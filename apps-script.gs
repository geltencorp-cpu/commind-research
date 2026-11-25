// =====================================================================
// 어르신 교통안전 검사 (콤마인드 연구용) - 구글 시트 Apps Script
// ※ 운영 중인 시트와 섞이지 않도록 연구용 시트를 새로 만들어 이 코드를 붙여 넣으세요.
// 시트에서 [확장 프로그램 → Apps Script]에 이 코드를 통째로 붙여 넣고,
// [배포 → 배포 관리 → 연필 아이콘 → 버전 "새 버전" → 배포]로 올리세요.
// =====================================================================

// 인사이트 페이지 비밀번호 (꼭 바꿔 주세요)
var INSIGHT_PASSWORD = '여기에-비밀번호';

// 열 제목과 퀴즈에서 보내는 항목 이름을 짝지은 목록 (이 순서대로 시트에 기록)
// 새 항목은 맨 뒤에 추가해야 예전 줄과 칸이 어긋나지 않습니다.
var COLUMNS = [
  ['위치', 'location'],
  ['기관명', 'institution'],
  ['일시', 'timestamp'],
  ['전화번호', 'phone'],
  ['안전 점수', 'safetyScore'],
  ['지남력', 'cog_orientation'],
  ['기억력', 'cog_memory'],
  ['주의력', 'cog_attention'],
  ['시공간', 'cog_visuospatial'],
  ['집행기능', 'cog_executive'],
  ['언어', 'cog_language'],
  ['반응속도', 'beh_avgReaction'],
  ['빈터치', 'beh_missedTaps'],
  ['연타', 'beh_multiTaps'],
  ['이탈', 'beh_focusLoss'],
  ['인지 건강 점수', 'cognitiveScore'],
  ['날짜(40)', 'cog_date'],
  ['계절(20)', 'cog_season'],
  ['흡연(20)', 'cog_smoking'],
  ['집중(20)', 'cog_focus'],
  ['건너기 누른 횟수', 'beh_signalPresses'],
  ['불필요한 누름', 'beh_signalExtra'],
  ['빨간불에 누름', 'beh_signalRed'],
  ['기록ID', 'recordId'],
  ['Q1 초록불 깜빡임', 'q1'],
  ['Q3 밤에 입는 옷', 'q3'],
  ['Q4 버스 하차', 'q4'],
  ['Q5 무단횡단', 'q5'],
  ['Q6 골목길 방향', 'q6'],
  ['Q8 신호 5초', 'q8'],
  ['Q9 복습: 버스 하차', 'q9'],
  ['Q10 복습: 골목길 방향', 'q10'],
  ['Q11 복습: 밤길 옷차림', 'q11'],
  ['Q12 복습: 나오지 않은 영상', 'q12'],
  ['Q2 흡연 단계', 'q2_smoking'],
  ['Q7 월', 'q7_month'],
  ['Q7 일', 'q7_day'],
  ['Q7 계절', 'q7_season'],
  ['Q13 시계', 'q13_clock'],
  ['Q14 신호등', 'q14_signal'],
  ['Q15 선 잇기', 'q15_match'],
  ['Q16 카드 위치 기억(0~4)', 'q16_memory'],
  ['ISO시각', 'isoTime'],
  ['Q1 고른 보기', 'q1_choice'],
  ['Q3 고른 보기', 'q3_choice'],
  ['Q4 고른 보기', 'q4_choice'],
  ['Q5 고른 보기', 'q5_choice'],
  ['Q6 고른 보기', 'q6_choice'],
  ['Q8 고른 보기', 'q8_choice'],
  ['Q9 고른 보기', 'q9_choice'],
  ['Q10 고른 보기', 'q10_choice'],
  ['Q11 고른 보기', 'q11_choice'],
  ['Q12 고른 보기', 'q12_choice'],
  ['상담 안내', 'consultLevel'],
  ['부족 영역', 'weakDomains'],
  // ----- [연구] 참여 번호 · 기본정보 -----
  ['연구 참여 번호', 'participantCode'],
  ['태어난 해', 'pf_birthYear'],
  ['나이(올해-태어난 해)', 'pf_age'],
  ['성별', 'pf_sex'],
  ['교육연수', 'pf_eduYears'],
  ['기기 사용(0안씀~3매일)', 'pf_digital'],
  ['주로 쓰는 손', 'pf_hand'],
  ['안경', 'pf_glasses'],
  ['보청기', 'pf_hearingAid'],
  ['손떨림·관절', 'pf_tremor'],
  ['기억 저하 호소(0~2)', 'pf_memoryComplaint'],
  ['어젯밤 잠(0~2)', 'pf_sleep'],
  ['진행자 대신 입력', 'pf_assisted'],
  // ----- [연구] 응답 과정 -----
  ['태어난 해 입력 시간(ms)', 'rp_yearTypingMs'],
  ['태어난 해 지운 횟수', 'rp_yearDeletes'],
  ['기본정보 답 바꾼 횟수', 'rp_changes'],
  ['기본정보1 소요(ms)', 'rp_profile1Ms'],
  ['기본정보2 소요(ms)', 'rp_profile2Ms'],
  // ----- [연구] 신호등 반응시간 -----
  ['신호등 초록 반응 평균(ms)', 'sig_goRtMean'],
  ['신호등 초록 반응 표준편차(ms)', 'sig_goRtSd'],
  ['신호등 초록 반응 수', 'sig_goN'],
  ['신호등 빨강 누름 평균(ms)', 'sig_nogoRtMean'],
  ['신호등 놓침', 'sig_omission'],
  ['신호등 빨강에 누름', 'sig_commission'],
  // ----- [연구] 영상 문제: 끝나기 전에 답했는지 -----
  ['영상 문제 수', 'vid_n'],
  ['영상 재생된 문제 수', 'vid_played'],
  ['영상 끝나기 전 답한 수', 'vid_early'],
  ['답할 때까지 본 비율 평균(%)', 'vid_watchPct'],
  ['영상 끝난 뒤 답까지 평균(ms)', 'vid_afterEndMs'],
  ['끝나기 전 답한 문제', 'vid_earlyList'],
  // ----- [연구] 센서 -----
  ['움직임 센서 수집', 'sensorMotion'],
  ['센서 허락', 'sensorPermission'],
  ['기록 형식 버전', 'logVersion'],
  // ----- [연구] 복습 퀴즈 (Q9~Q12, 기억력 보조 지표). 예전 줄과 칸이 어긋나지 않도록 맨 뒤에 둠 -----
  ['복습 문제 수', 'rv_n'],
  ['복습 맞힌 수', 'rv_correct'],
  ['복습 기억안남 선택 수', 'rv_dontKnow'],
  ['복습 반응 평균(ms)', 'rv_rtMean'],
  ['복습 맞힌 문제 반응 평균(ms)', 'rv_rtCorrectMean'],
  ['원래 문제 맞힌 수(복습 대상)', 'rv_learned'],
  ['배운 것 중 복습도 맞힌 수', 'rv_retained'],
  ['기억 유지율', 'rv_retention'],
  ['배운 뒤 복습까지 평균(초)', 'rv_delaySec'],
  ['출처 기억(Q12) 맞힘', 'rv_sourceOk'],
  ['복습 문제별 결과', 'rv_detail'],
  // ----- [연구] Q17 1-back (기억력 주요 지표, 기록형식 3) -----
  ['1-back 판단 수', 'nb_n'],
  ['1-back 맞힌 수', 'nb_correct'],
  ['1-back 오답률', 'nb_errRate'],
  ['1-back 같은데 놓침', 'nb_missSame'],
  ['1-back 다른데 같다고 함', 'nb_falseSame'],
  ['1-back 무응답', 'nb_timeout'],
  ['1-back 반응 평균(ms)', 'nb_rtMean'],
  ['1-back 맞힌 반응 평균(ms)', 'nb_rtCorrectMean'],
  // ----- [연구] Q18 신호등 2회차 (집중력: 처음보다 느려지거나 놓치는지) -----
  ['신호등2 초록 반응 평균(ms)', 'sig2_goRtMean'],
  ['신호등2 초록 반응 표준편차(ms)', 'sig2_goRtSd'],
  ['신호등2 초록 반응 수', 'sig2_goN'],
  ['신호등2 놓침', 'sig2_omission'],
  ['신호등2 빨강에 누름', 'sig2_commission'],
  ['반응 저하(2회차÷1회차)', 'sig_rtDrift'],
  ['놓침 증가(2회차-1회차)', 'sig_omissionDrift'],
  // ----- [연구] 진행자가 입력한 코그메이트 결과 (비교 기준) -----
  ['코그메이트 집중력', 'cg_attention'],
  ['코그메이트 기억력', 'cg_memory'],
  ['코그메이트 뇌나이', 'cg_brainAge'],
  ['검사 순서', 'cg_order'],
  ['진행자 메모', 'cg_note'],
  ['코그메이트 입력 시각', 'cg_enteredAt'],
  // ----- [연구] Q16 카드 위치 기억 (기록형식 4) -----
  ['카드 문제 수', 'cd_n'],
  ['카드 맞힌 수', 'cd_hits'],
  ['카드 고르기 평균(ms)', 'cd_rtMean'],
  ['카드 위치 오차 평균(칸)', 'cd_distMean'],
  ['카드 문제별 결과', 'cd_detail'],
  // ----- [연구] 영상 1분 잠금 (기록형식 5): 잠긴 동안 답을 누른 횟수 = 조급함 -----
  ['영상 잠금 중 누른 수', 'vid_lockedTaps'],
  ['잠금 중 누른 문제', 'vid_lockedTapQs'],
  ['영상 잠금 풀린 이유', 'vid_unlock']
];

// [연구] 원시 행동 기록을 저장할 드라이브 폴더 이름
var RAW_FOLDER_NAME = 'COMMIND_원시기록';

function keyIndex(key) {
  for (var i = 0; i < COLUMNS.length; i++) if (COLUMNS[i][1] === key) return i;
  return -1;
}

function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

// '기관' 탭: 기관명 / 위도 / 경도 / 반경(m). 없으면 맨 뒤에 새로 만듦
function getInstSheet(ss) {
  var sh = ss.getSheetByName('기관');
  if (!sh) {
    sh = ss.insertSheet('기관', ss.getSheets().length);
    sh.getRange(1, 1, 1, 4).setValues([['기관명', '위도', '경도', '반경(m)']]);
  }
  return sh;
}

function readInstitutions(ss) {
  var sh = getInstSheet(ss);
  var list = [];
  if (sh.getLastRow() > 1) {
    sh.getRange(2, 1, sh.getLastRow() - 1, 4).getValues().forEach(function (v) {
      if (v[0] !== '') list.push({ name: String(v[0]).trim(), lat: v[1], lng: v[2], radius: v[3] });
    });
  }
  return list;
}

// 검사 화면에서 처음 쓴 기관 이름이면 위치와 함께 '기관' 탭에 자동 등록
function registerInstitution(ss, name, location) {
  name = String(name || '').trim();
  if (!name) return;
  var m = /(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)/.exec(String(location || ''));
  if (!m) return;
  var exists = readInstitutions(ss).some(function (i) { return i.name === name; });
  if (!exists) getInstSheet(ss).appendRow([name, Number(m[1]), Number(m[2]), '']);
}

// [연구] 원시 기록 폴더 (없으면 내 드라이브에 새로 만듦)
function getRawFolder() {
  var it = DriveApp.getFoldersByName(RAW_FOLDER_NAME);
  return it.hasNext() ? it.next() : DriveApp.createFolder(RAW_FOLDER_NAME);
}

// [연구] '원시기록' 탭: 기록ID / 연구 참여 번호 / 저장 시각 / 파일 이름 / 파일 주소 / 크기(KB) / 터치 수 / 움직임 수 / 이벤트 수
function getRawSheet(ss) {
  var sh = ss.getSheetByName('원시기록');
  if (!sh) {
    sh = ss.insertSheet('원시기록', ss.getSheets().length);
    sh.getRange(1, 1, 1, 9).setValues([['기록ID', '연구 참여 번호', '저장 시각', '파일 이름', '파일 주소', '크기(KB)', '터치 수', '움직임 수', '이벤트 수']]);
  }
  return sh;
}

// [연구] 원시 행동 기록을 드라이브에 JSON 파일로 저장 (같은 기록ID면 덮어씀)
function saveRaw(ss, data) {
  var id = String(data.recordId || '').replace(/[^A-Za-z0-9_-]/g, '');
  if (!id) return;
  var code = String(data.participantCode || '').replace(/[^A-Za-z0-9가-힣_-]/g, '');
  var name = (code ? code + '_' : '') + id + '.json';
  var text = JSON.stringify(data.raw || {});
  var folder = getRawFolder();
  var old = folder.getFilesByName(name);
  while (old.hasNext()) old.next().setTrashed(true);
  var file = folder.createFile(name, text, 'application/json');
  var c = (data.raw && data.raw.counts) || {};
  var rawSheet = getRawSheet(ss);
  rawSheet.getRange(1, 2, rawSheet.getMaxRows(), 1).setNumberFormat('@');
  rawSheet.appendRow([data.recordId, String(data.participantCode || ''), new Date(), name, file.getUrl(),
    Math.round(text.length / 1024), c.touch || 0, c.motion || 0, c.events || 0]);
}

// 퀴즈 결과 저장
function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheets()[0];
    var data = JSON.parse(e.postData.contents);

    // [연구] 원시 기록은 드라이브 파일로 저장하고 끝
    if (data.type === 'raw') {
      saveRaw(ss, data);
      return ContentService.createTextOutput('OK');
    }

    // 예전 표(첫 열이 '일시')라면 맨 앞에 '위치' 열을 한 번만 끼워 넣음
    if (sheet.getLastRow() > 0 && sheet.getRange(1, 1).getValue() === '일시') {
      sheet.insertColumnBefore(1);
    }
    // '기관명' 열이 없는 표라면 '위치' 바로 뒤에 한 번만 끼워 넣음
    if (sheet.getLastRow() > 0) {
      var head = sheet.getRange(1, 1, 1, Math.max(1, sheet.getLastColumn())).getValues()[0];
      if (head.indexOf('기관명') === -1) sheet.insertColumnBefore(2);
    }

    var headers = COLUMNS.map(function (c) { return c[0]; });
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);

    // 전화번호 열은 글자 형식으로 두어 맨 앞 0이 사라지지 않게 함
    sheet.getRange(1, keyIndex('phone') + 1, sheet.getMaxRows(), 1).setNumberFormat('@');
    // [연구] 참여 번호도 글자 형식 (001 이 1 로 바뀌면 코그메이트 결과와 이을 수 없음)
    sheet.getRange(1, keyIndex('participantCode') + 1, sheet.getMaxRows(), 1).setNumberFormat('@');

    // 같은 기록ID가 이미 있는 줄 찾기
    var idCol = keyIndex('recordId') + 1;
    var target = 0;
    if (data.recordId && sheet.getLastRow() > 1) {
      var ids = sheet.getRange(2, idCol, sheet.getLastRow() - 1, 1).getValues();
      for (var i = ids.length - 1; i >= 0; i--) {
        if (ids[i][0] === data.recordId) { target = i + 2; break; }
      }
    }

    // 그 줄이 있으면, 이번에 보내지 않은 칸은 원래 값을 지킴 (예: 코그메이트 점수를 넣은 뒤 상담 신청을 다시 보내도 지워지지 않게)
    var old = target ? sheet.getRange(target, 1, 1, COLUMNS.length).getValues()[0] : null;
    var row = COLUMNS.map(function (c, k) {
      var value = data[c[1]];
      if (value === undefined || value === null) return old ? old[k] : '';
      return value;
    });

    if (target) {
      sheet.getRange(target, 1, 1, row.length).setValues([row]);
    } else {
      sheet.appendRow(row);
    }

    // [연구] 코그메이트 결과만 덧붙인 전송이면 기관 등록 등은 건너뜀
    if (data.type === 'cogmate') return ContentService.createTextOutput('OK');

    registerInstitution(ss, data.institution, data.location);
  } finally {
    lock.releaseLock();
  }
  return ContentService.createTextOutput('OK');
}

function doGet(e) {
  var p = (e && e.parameter) ? e.parameter : {};
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  // 검사 화면용: 가까운 기관을 고를 수 있도록 기관 이름과 좌표만 돌려줌 (비밀번호 없음)
  if (p.action === 'places') {
    var places = readInstitutions(ss).map(function (i) { return { name: i.name, lat: i.lat, lng: i.lng }; });
    return json({ ok: true, places: places });
  }

  // 인사이트 페이지용: 비밀번호가 맞으면 전화번호를 뺀 기록과 기관 목록을 돌려줌
  if (INSIGHT_PASSWORD === '여기에-비밀번호') {
    return json({ ok: false, error: '시트 스크립트에서 비밀번호를 먼저 정해 주세요.' });
  }
  if (!p.pw || p.pw !== INSIGHT_PASSWORD) {
    return json({ ok: false, error: '비밀번호가 맞지 않습니다.' });
  }

  var sheet = ss.getSheets()[0];
  var titleToKey = {};
  COLUMNS.forEach(function (c) { titleToKey[c[0]] = c[1]; });

  var rows = [];
  if (sheet.getLastRow() > 1) {
    var values = sheet.getRange(1, 1, sheet.getLastRow(), sheet.getLastColumn()).getValues();
    var head = values[0];
    for (var r = 1; r < values.length; r++) {
      var o = {};
      for (var c = 0; c < head.length; c++) {
        var key = titleToKey[head[c]];
        if (!key) continue;
        var v = values[r][c];
        if (v instanceof Date) v = v.toISOString();
        o[key] = v;
      }
      o.hasPhone = !!o.phone;   // 상담 신청 여부만 남기고
      delete o.phone;           // 전화번호와 기록ID는 내보내지 않음
      delete o.recordId;
      rows.push(o);
    }
  }

  return json({ ok: true, rows: rows, institutions: readInstitutions(ss) });
}
