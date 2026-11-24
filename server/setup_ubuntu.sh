#!/usr/bin/env bash
# 콤마인드 AI 서버 한 번에 설치 (우분투)
#
#   bash server/setup_ubuntu.sh              # 전부 (패키지 + 파이썬 + 시연 모델 + 올라마 + 점검)
#   bash server/setup_ubuntu.sh --no-ollama  # 올라마 빼고
#   bash server/setup_ubuntu.sh --service    # 끝나고 컴퓨터 켜면 자동 실행까지 등록
#
# 여러 번 실행해도 됩니다 (이미 된 단계는 건너뜀). 마지막에 '점검 결과'가 나오니 그대로 복사해 주세요.
set -euo pipefail

MODEL="${OLLAMA_MODEL:-exaone3.5:7.8b}"
PORT="${PORT:-8000}"
NO_OLLAMA=0; SERVICE=0; NO_APT=0
for a in "$@"; do
  case "$a" in
    --no-ollama) NO_OLLAMA=1 ;;
    --service) SERVICE=1 ;;
    --no-apt) NO_APT=1 ;;
  esac
done

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
step() { echo; echo "=== $* ==="; }

if [ "$NO_APT" = 0 ]; then
  step "1/6 기본 패키지"
  if ! python3 -m venv --help >/dev/null 2>&1 || ! command -v curl >/dev/null; then
    sudo apt-get update -y && sudo apt-get install -y python3-venv python3-pip curl git
  else
    echo "이미 있음"
  fi
fi

step "2/6 파이썬 환경 (.venv)"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
python3 -c "import fastapi, xgboost, sklearn; print('파이썬 패키지 OK')"

step "3/6 시연용 모델 (가상 100명, 모의 연구 – 가상 데이터)"
mkdir -p data models
if [ -f data/training.csv ]; then
  echo "현장 학습표(data/training.csv)가 있어 그것으로 학습합니다"
  python3 train.py --data data/training.csv --source real --note "현장 데이터"
else
  [ -f data/virtual_training.csv ] || python3 make_virtual_training.py -n 100 -o data/virtual_training.csv
  python3 train.py --data data/virtual_training.csv --source virtual --note "시연용 가상 100명"
fi

if [ "$NO_OLLAMA" = 0 ]; then
  step "4/6 올라마 + 언어모델 ($MODEL)"
  if ! command -v ollama >/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
  else
    echo "올라마 이미 있음: $(ollama --version 2>/dev/null | head -1)"
  fi
  for i in $(seq 1 15); do curl -s http://127.0.0.1:11434/api/tags >/dev/null && break; sleep 2; done
  ollama pull "$MODEL"
else
  step "4/6 올라마 건너뜀"
fi

if [ "$SERVICE" = 1 ]; then
  step "5/6 자동 실행 등록 (commind-ai)"
  sudo tee /etc/systemd/system/commind-ai.service >/dev/null <<EOF
[Unit]
Description=COMMIND AI server
After=network-online.target ollama.service
[Service]
User=$USER
WorkingDirectory=$HERE
Environment=OLLAMA_MODEL=$MODEL
ExecStart=$HERE/.venv/bin/uvicorn app:app --host 0.0.0.0 --port $PORT
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable --now commind-ai
  sleep 4
else
  step "5/6 자동 실행 등록 건너뜀 (원하면 --service)"
fi

step "6/6 점검"
OLLAMA_MODEL="$MODEL" python3 selfcheck.py
echo
if [ "$SERVICE" = 1 ]; then
  echo "서버 실행 중: http://$(hostname -I | awk '{print $1}'):$PORT"
else
  echo "서버 켜기:  cd $HERE && . .venv/bin/activate && OLLAMA_MODEL=$MODEL uvicorn app:app --host 0.0.0.0 --port $PORT"
fi
