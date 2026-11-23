# 콤마인드 연구용 검사 (commind-research)

운영 중인 [silver_traffic-](https://github.com/geltencorp-cpu/silver_traffic-)를 복사해 만든 **연구용** 저장소입니다.
대일리랩 / 김산 석사과정 연구에서 행동데이터를 수집하고, 코그메이트 결과와 비교하기 위해 사용합니다.
운영 서비스와 데이터가 섞이지 않도록 **구글 시트와 Apps Script를 따로** 씁니다.

## 파일

| 파일 | 내용 |
| --- | --- |
| `index.html` | 검사 화면 (기본정보 → 표지판 기억 → Q1~Q16 → 결과) |
| `research-logger.js` | 원시 행동 기록기 (터치·기기 움직임·기울기·과제 이벤트) |
| `apps-script.gs` | 구글 시트 저장 스크립트 (요약은 시트, 원시 기록은 드라이브) |
| `insights.html` | 기관별 인사이트 페이지 (운영판과 같음) |

## 1단계에서 바뀐 것

1. **기본정보 화면 2장**
   - 필수: 태어난 해, 성별, 학교, 스마트폰·태블릿 사용, 주로 쓰는 손
   - 선택: 안경, 보청기, 손 떨림·관절, 기억 저하 호소, 어젯밤 잠
   - 진행자가 대신 입력했는지 표시
2. **연구 참여 번호**: 시작 화면에서 진행자가 입력합니다(예: P001). 코그메이트 결과와 같은 사람을 잇는 열쇠입니다.
3. **응답 과정 기록**: 태어난 해 입력 시간과 지운 횟수, 답을 바꾼 횟수, 화면별 소요 시간을 남깁니다.
4. **신호등 과제(Q14) 시도별 반응시간**: 불이 화면에 그려진 시각부터 손가락이 닿은 시각까지 ms로 잽니다.
   - 시트에는 초록 반응 평균·표준편차, 빨강에 누른 반응 평균, 놓침, 빨강에 누름을 저장합니다.
5. **원시 행동 기록** (`research-logger.js`)
   - 터치: 누름/이동/뗌, 좌표, 접촉 크기, 압력, 누른 대상의 위치·크기
   - 기기 움직임(가속도·회전): 약 50Hz
   - 기울기(alpha·beta·gamma): 약 20Hz
   - 화면마다 버튼 배치: 빈 곳 터치가 어느 버튼에 가까웠는지 계산하는 데 씁니다.
   - 시계 그리기 획 좌표, 선 잇기 연결, 기억 과제 선택, 문항별 응답
6. **저장**
   - 요약 한 줄은 시트 첫 탭에 저장합니다(기존 열 뒤에 연구용 열 추가).
   - 원시 기록은 드라이브 `COMMIND_원시기록` 폴더에 `참여번호_기록ID.json`으로 저장하고, `원시기록` 탭에 목록을 남깁니다.

7. **복습 퀴즈 Q9~Q12 (기억력 보조 지표, logVersion 2)**
   - 앞에서 본 영상 내용을 다시 묻습니다. Q9 ← Q4 버스, Q10 ← Q6 골목길, Q11 ← Q3 밤길 옷차림, Q12는 "오늘 영상에 나오지 않은 내용"(출처 기억).
   - 모든 문제에 "잘 기억나지 않아요" 보기가 있고, 섞지 않고 맨 아래에 둡니다.
   - 시트 열 `rv_*`: 맞힌 수, 모른다 선택 수, 반응시간, 원래 문제를 맞힌 것 중 복습도 맞힌 비율(기억 유지율), 배운 뒤 복습까지 시간, 출처 기억.
   - 분석 지표 M01~M06 (`extract_features.py`). B19(교통문제 오답률)는 기록형식 2부터 복습 문제를 뺍니다.
   - 보기를 섞은 뒤 화면 번호(①②③)는 위에서부터 다시 매기고, 기록에는 원래 보기 번호가 남습니다.

## 연구용 시트 연결하기

1. 새 구글 시트를 만듭니다. 운영 시트와 다른 시트여야 합니다.
2. **확장 프로그램 → Apps Script**를 열고 `apps-script.gs` 내용을 통째로 붙여 넣습니다.
3. `INSIGHT_PASSWORD`를 바꿉니다.
4. **배포 → 새 배포 → 웹 앱**으로 배포합니다.
   - 실행: 나
   - 액세스: 모든 사용자
   - 처음 배포할 때 드라이브 권한을 허락해야 합니다.
5. 나온 주소(`https://script.google.com/macros/s/.../exec`)를 `index.html`의 `googleScriptURL`과 `insights.html`의 `SCRIPT_URL`에 넣습니다.

주소를 넣기 전에는 검사는 되지만 아무것도 저장되지 않습니다(콘솔에 안내만 나옴).

## 원시 기록 형식 (logVersion 1)

```
{
  version, recordId, startedAt, endedAt, durationMs, device{...}, sensorPermission, motionSeen,
  touchCols:   [t, kind(d/m/u/c), id, x, y, w, h, pressure, type, slide],   touch: [[...], ...]
  motionCols:  [t, ax, ay, az, rAlpha, rBeta, rGamma],                        motion: [[...], ...]
  orientationCols: [t, alpha, beta, gamma],                                   orientation: [[...], ...]
  eventCols:   [t, type, slide, data],                                        events: [[...], ...]
  layouts: [{ t, slide, vw, vh, items: [[tag, class, name, x, y, w, h], ...] }],
  extra: { summary, profile, profileMeta }
}
```

- `t`는 검사 시작부터 흐른 ms입니다. 좌표는 CSS 픽셀입니다.
- 주요 이벤트: `slide`, `tap_target`, `answer`, `date_answer`, `profile_pick`, `profile_year`, `signal_on`, `signal_paint`, `signal_press`(rt 포함), `signal_off`, `clock_submit`, `match_submit`, `recall_submit`, `visibility`, `resize`
- 10분 검사 한 번에 약 1~2MB입니다.

## 알아둘 점

- **아이폰·아이패드 센서 허락**: [시작하기]를 누를 때 "동작 및 방향" 허락 창이 뜹니다. 거부하면 `sensorPermission`이 `denied`로 남고, 터치 기록만 수집됩니다.
- **센서와 주소**: 기기 움직임 센서는 `https` 주소에서만 동작합니다. GitHub Pages는 해당됩니다.
- **터치 압력**: 대부분 태블릿은 실제 압력을 주지 않습니다. 분석에서는 접촉 크기(w, h)를 씁니다.
- **나이**: 올해에서 태어난 해를 뺀 값이라, 생일이 지나지 않았으면 1살 많게 나옵니다.
- **전송 성공 여부**: 기존 방식(no-cors)이라 화면에서는 확인할 수 없습니다. 드라이브 폴더와 `원시기록` 탭에서 확인하세요.

## 분석: 원시 기록 → 지표 표

`analysis/extract_features.py`는 드라이브 `COMMIND_원시기록` 폴더의 JSON 파일들을 사람별 지표 한 줄씩의 CSV로 바꿉니다.
열 이름 앞의 코드(B01, C01 …)는 `수집 데이터 정의서`의 지표 코드입니다.

```
pip install numpy pandas scipy
python3 analysis/extract_features.py <내려받은 폴더> -o features.csv
```

- 결과 CSV는 엑셀에서 바로 열립니다(UTF-8 BOM).
- 이 CSV를 참여 번호로 코그메이트 결과와 이어 붙여 분석합니다.
- 계산할 수 없는 지표는 빈칸입니다.
  - 센서가 없는 기기(PC)는 기울기·떨림 지표가 비어 있습니다.
  - 지금 콘텐츠에 해당 장면이 없는 지표(B15, B21, B22, C06~C08)는 아직 만들지 않았습니다.
- `_`로 시작하는 열은 품질 확인용입니다(버튼 터치 수, 불안정 구간 터치 수 등).
- 기울기는 기기를 드는 각도 자체가 아니라, **그 사람의 평소 각도에서 벗어난 정도**로 잽니다. 드는 습관이 사람마다 달라서입니다.
- **접촉 면적(B12)** 은 기기가 실제 손가락 크기를 알려줄 때만 의미가 있습니다. 1~2처럼 아주 작은 값만 나오면 그 기기는 지원하지 않는 것입니다.
- **연구 데이터(JSON, CSV)는 저장소에 올리지 마세요.** 개인정보가 포함될 수 있습니다.
