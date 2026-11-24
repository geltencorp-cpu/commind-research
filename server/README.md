# 콤마인드 AI 서버 (우리 서버에서 돌리는 자체 AI)

태블릿 앱이 남긴 **원시 행동 기록**을 받아 우리 서버 안에서만 계산합니다. 외부 AI 서비스로 데이터를 보내지 않습니다.

```
원시 기록(JSON) → ① 지표 추출 → ② 예측 AI(자체 학습) → ③ 점수·근거 → ④ 리포트 에이전트(올라마 로컬 언어모델)
                                      ↑ 학습할 때 정답: 코그메이트 점수
```

| 단계 | 하는 일 | 파일 |
|---|---|---|
| ① 지표 추출 | 원시 기록 → B01·N01·D01·M02 등 지표 | `../analysis/extract_features.py` |
| ② 예측 AI | 지표 + 기본정보(보정) → 코그메이트 척도의 주의·집중력·기억력(0~50), 뇌 나이 | `commind_ai/model.py` |
| ③ 근거 | 사람마다 어떤 지표가 점수를 올리고 내렸는지 (XGBoost SHAP 값 / 선형 기여도) | 〃 |
| ④ 리포트 | 예측 숫자와 근거만 받아 쉬운 말로 설명. 안전장치가 다른 숫자·병명·진단 표현을 걸러 냄 | `commind_ai/report.py` |

- **모델 고르기**: 규제 선형회귀와 XGBoost를 '한 명씩 빼고 확인(LOOCV)'으로 비교해 평균 오차가 작은 쪽을 자동으로 고릅니다. 데이터가 적을 때는 단순한 모델이, 많아지면 XGBoost가 뽑힐 수 있습니다.
- **뇌 나이**: 나이 + 두 예측 점수. 학습에 쓰지 않은 사람 기준의 예측 점수(교차검증 예측)로 학습해 성능이 부풀려지지 않게 했습니다.
- **언어모델은 점수를 계산하지 않습니다.** 숫자를 지어낼 수 있기 때문입니다. 계산은 ② 예측 AI가 하고, 언어모델은 설명만 합니다. 올라마가 꺼져 있으면 기본 문장(규칙)으로 리포트가 나옵니다.
- **받은 기록은 저장하지 않습니다.** 올린 파일은 계산이 끝나면 사라집니다.

## 우분투(26.10)에 설치

### 한 번에 설치 (추천)
```bash
git clone https://github.com/geltencorp-cpu/commind-research.git ~/commind-research
bash ~/commind-research/server/setup_ubuntu.sh --service
```
패키지 → 파이썬 환경 → 시연 모델 → 올라마·언어모델 → 자동 실행 등록 → 점검까지 차례로 합니다. 중간에 관리자 비밀번호(sudo)를 물을 수 있습니다.
마지막의 `[점검 결과 시작] ~ [점검 결과 끝]`을 복사해 두면 문제를 찾기 쉽습니다.

### 직접 하나씩 설치

```bash
# 1. 기본 도구
sudo apt update && sudo apt install -y python3-venv git curl

# 2. 코드 받기 (/opt 아래에 둘 경우)
sudo git clone https://github.com/geltencorp-cpu/commind-research.git /opt/commind-research
sudo chown -R $USER /opt/commind-research
cd /opt/commind-research/server

# 3. 파이썬 환경
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# 4. 시연용 모델 만들기 (가상 100명, 모의 연구 – 가상 데이터)
python3 make_virtual_training.py -n 100 -o data/virtual_training.csv
python3 train.py --data data/virtual_training.csv --source virtual --note "시연용 가상 100명"

# 5. 올라마 + 한국어 언어모델
curl -fsSL https://ollama.com/install.sh | sh
ollama pull exaone3.5:7.8b          # 약 4.8GB. 메모리가 적으면 exaone3.5:2.4b

# 6. 실행 → 같은 와이파이의 다른 기기에서 http://서버IP:8000 접속
uvicorn app:app --host 0.0.0.0 --port 8000
```

- 언어모델 바꾸기: `OLLAMA_MODEL=exaone3.5:2.4b uvicorn app:app ...`
- **라이선스**: EXAONE 3.5는 비상업(NC) 라이선스입니다. 졸업 작품·연구에는 쓸 수 있지만, 회사 서비스로 팔 때는 상업 이용이 허락된 모델로 바꾸고 라이선스를 확인하세요.
- 파이썬 버전 때문에 4단계 설치가 실패하면 `uv`로 파이썬 3.12 환경을 만들어 설치하세요.
- 그래픽카드가 없어도 돌아가지만 리포트 한 번에 수십 초 걸릴 수 있습니다.

### 컴퓨터를 켜면 자동 실행
```bash
sudo cp commind-ai.service /etc/systemd/system/     # 안의 User= 를 내 사용자 이름으로 고치기
sudo systemctl daemon-reload && sudo systemctl enable --now commind-ai
```
올라마는 설치할 때 자동 실행으로 등록됩니다.

## 시연 화면 (http://서버IP:8000)

- 왼쪽에서 참여자를 누르면 **그 사람을 빼고 학습한 모델의 예측**과 코그메이트 실제 점수를 나란히 보여 줍니다.
- 앱 원시 기록 파일(드라이브 `COMMIND_원시기록` 폴더의 JSON)을 올리면 바로 예측하고 리포트를 씁니다.
- 7개 능력: 주의력·집중력·기억력은 **AI 예측**, 지남력·시공간·집행기능·언어는 앱의 **규칙 점수(검증 전)** 로 표시됩니다.
- 모델 카드: 학습 데이터, 고른 모델, 교차검증 정확도(r, 평균 오차, 등급 일치), 중요 지표
- API 문서: http://서버IP:8000/docs

## 현장 데이터로 다시 학습

```bash
python3 ../analysis/extract_features.py ~/내려받은/COMMIND_원시기록 -o data/features.csv
# 구글 시트 첫 탭을 CSV로 내려받아 data/sheet.csv 로 저장
python3 build_training.py data/features.csv data/sheet.csv -o data/training.csv
python3 train.py --data data/training.csv --source real --note "현장 1차"
sudo systemctl restart commind-ai
```
T로 시작하는 참여번호(진행자 시험), 코그메이트 집중력 0.0(검사 미완료), 같은 사람의 두 번째 검사는 자동으로 빠집니다.
학습 데이터 파일(`data/`)과 모델(`models/`)은 저장소에 올리지 않습니다.
