// =====================================================================
// 콤마인드 연구용 원시 행동 기록기 (ResearchLog)
//
// 검사 한 번(세션) 동안 다음을 시간 순서대로 기록합니다.
//   - 터치(포인터): 누름/이동/뗌, 좌표, 접촉 크기, 압력, 누른 대상의 위치·크기
//   - 기기 움직임: 가속도(중력 포함), 회전 속도 (약 50Hz)
//   - 기기 기울기: alpha / beta / gamma (약 20Hz)
//   - 화면 이동, 문항 응답, 과제 이벤트(신호등 시도별 반응시간 등)
//   - 화면마다 누를 수 있는 요소들의 위치(레이아웃) — 빈 곳 터치가 어느 버튼에 가까웠는지 나중에 계산
//
// 모든 시각(t)은 세션 시작부터 흐른 ms (performance.now 기준, 소수 1자리)입니다.
// 저장 형식은 열(column) 이름 + 2차원 배열이라 용량이 작습니다. 분석 코드에서 표로 바로 바꿀 수 있습니다.
// =====================================================================
const ResearchLog = (() => {
    const VERSION = 1;
    const MOTION_MS = 20;   // 가속도·회전: 최소 20ms 간격 (약 50Hz)
    const ORIENT_MS = 50;   // 기울기: 최소 50ms 간격 (약 20Hz)
    const MOVE_MS = 16;     // 손가락 이동: 최소 16ms 간격

    let s = null;           // 현재 세션
    let listening = false;
    let lastMotion = -1e9, lastOrient = -1e9;
    const lastMove = {};    // pointerId별 마지막 이동 기록 시각
    const down = {};        // pointerId별 누르고 있는 중인지

    const now = () => performance.now();
    const rel = (t) => s ? Math.round((t - s.t0) * 10) / 10 : 0;
    const r2 = (v) => (v === null || v === undefined || isNaN(v)) ? null : Math.round(v * 100) / 100;
    const r1 = (v) => (v === null || v === undefined || isNaN(v)) ? null : Math.round(v * 10) / 10;

    function activeSlide() {
        const el = document.querySelector('.slide-container.active');
        return el ? el.id.replace(/^page-/, '') : '';
    }

    // 누른 대상: 버튼·그림·캔버스 등 의미 있는 요소를 찾아 이름과 화면 위치를 남김
    const TARGETS = 'button, .sign-item, .match-item, canvas, input, a, .media-wrapper';
    function describe(el) {
        if (!el || !el.closest) return null;
        const t = el.closest(TARGETS);
        if (!t) return null;
        const b = t.getBoundingClientRect();
        let name = t.id || t.dataset.key || t.dataset.opt || t.dataset.v || (t.textContent || '').trim().slice(0, 12);
        const cls = (t.className && typeof t.className === 'string') ? t.className.split(/\s+/).filter(c => c && c !== 'btn-action')[0] || '' : '';
        return { tag: t.tagName.toLowerCase(), cls, name: String(name), x: r1(b.left), y: r1(b.top), w: r1(b.width), h: r1(b.height) };
    }

    // 지금 화면에서 누를 수 있는 요소들의 위치 목록
    function snapshotLayout(slideId) {
        const page = document.getElementById('page-' + slideId);
        if (!page) return;
        const items = [];
        page.querySelectorAll(TARGETS).forEach(el => {
            const b = el.getBoundingClientRect();
            if (b.width === 0 || b.height === 0) return;
            const d = describe(el);
            if (d) items.push([d.tag, d.cls, d.name, d.x, d.y, d.w, d.h]);
        });
        s.layouts.push({ t: rel(now()), slide: slideId, vw: window.innerWidth, vh: window.innerHeight, items });
    }

    // ---------- 터치(포인터) ----------
    // 열: t, 종류(d=누름 m=이동 u=뗌 c=취소), 손가락 번호, x, y, 접촉 너비, 접촉 높이, 압력, 입력 종류(t/m/p), 화면
    function onPointer(e) {
        if (!s) return;
        const kind = { pointerdown: 'd', pointermove: 'm', pointerup: 'u', pointercancel: 'c' }[e.type];
        if (kind === 'm') {
            if (!down[e.pointerId]) return;                       // 누르지 않은 채 움직이는 마우스는 기록 안 함
            if (e.timeStamp - (lastMove[e.pointerId] || 0) < MOVE_MS) return;
            lastMove[e.pointerId] = e.timeStamp;
        }
        if (kind === 'd') down[e.pointerId] = true;
        if (kind === 'u' || kind === 'c') delete down[e.pointerId];
        const slide = activeSlide();
        s.touch.push([rel(e.timeStamp), kind, e.pointerId, r1(e.clientX), r1(e.clientY),
            r1(e.width), r1(e.height), r2(e.pressure), (e.pointerType || '')[0] || '', slide]);
        if (kind === 'd') {
            const d = describe(e.target);
            s.events.push([rel(e.timeStamp), 'tap_target', slide, d ? { ...d, px: r1(e.clientX), py: r1(e.clientY) } : { none: true, px: r1(e.clientX), py: r1(e.clientY) }]);
        }
    }

    // ---------- 기기 움직임 · 기울기 ----------
    function onMotion(e) {
        if (!s) return;
        const t = now();
        if (t - lastMotion < MOTION_MS) return;
        lastMotion = t;
        const a = e.accelerationIncludingGravity || {}, rr = e.rotationRate || {};
        s.motion.push([rel(t), r2(a.x), r2(a.y), r2(a.z), r1(rr.alpha), r1(rr.beta), r1(rr.gamma)]);
        s.motionSeen = true;
    }
    function onOrientation(e) {
        if (!s) return;
        const t = now();
        if (t - lastOrient < ORIENT_MS) return;
        lastOrient = t;
        s.orientation.push([rel(t), r1(e.alpha), r1(e.beta), r1(e.gamma)]);
        s.orientSeen = true;
    }

    function onVisibility() { if (s) s.events.push([rel(now()), 'visibility', activeSlide(), { hidden: document.hidden }]); }
    function onResize() { if (s) s.events.push([rel(now()), 'resize', activeSlide(), { vw: window.innerWidth, vh: window.innerHeight, orient: (screen.orientation && screen.orientation.type) || '' }]); }

    function listen() {
        if (listening) return;
        listening = true;
        ['pointerdown', 'pointermove', 'pointerup', 'pointercancel'].forEach(t => document.addEventListener(t, onPointer, { capture: true, passive: true }));
        window.addEventListener('devicemotion', onMotion, { passive: true });
        window.addEventListener('deviceorientation', onOrientation, { passive: true });
        document.addEventListener('visibilitychange', onVisibility);
        window.addEventListener('resize', onResize);
    }

    return {
        // 아이폰·아이패드는 기기 움직임 센서를 쓰려면 버튼을 누른 순간에 허락을 받아야 합니다.
        // 반드시 [시작하기] 같은 버튼 클릭 처리 안에서 불러 주세요.
        requestSensors() {
            const asks = [];
            try {
                if (window.DeviceMotionEvent && typeof DeviceMotionEvent.requestPermission === 'function') asks.push(DeviceMotionEvent.requestPermission());
                if (window.DeviceOrientationEvent && typeof DeviceOrientationEvent.requestPermission === 'function') asks.push(DeviceOrientationEvent.requestPermission());
            } catch (e) { /* 허락 요청을 지원하지 않는 기기 */ }
            return Promise.all(asks.map(p => p.catch(() => 'error'))).then(r => {
                const state = r.length ? (r.every(x => x === 'granted') ? 'granted' : 'denied') : 'not-required';
                if (s) s.sensorPermission = state;
                return state;
            });
        },

        begin(recordId) {
            listen();
            lastMotion = lastOrient = -1e9;
            s = {
                version: VERSION, recordId, t0: now(), startedAt: new Date().toISOString(),
                device: {
                    ua: navigator.userAgent, platform: navigator.platform || '', lang: navigator.language,
                    screenW: screen.width, screenH: screen.height, dpr: window.devicePixelRatio,
                    vw: window.innerWidth, vh: window.innerHeight, maxTouch: navigator.maxTouchPoints || 0,
                    orient: (screen.orientation && screen.orientation.type) || ''
                },
                sensorPermission: 'unknown', motionSeen: false, orientSeen: false,
                touchCols: ['t', 'kind', 'id', 'x', 'y', 'w', 'h', 'pressure', 'type', 'slide'],
                motionCols: ['t', 'ax', 'ay', 'az', 'rAlpha', 'rBeta', 'rGamma'],
                orientationCols: ['t', 'alpha', 'beta', 'gamma'],
                eventCols: ['t', 'type', 'slide', 'data'],
                touch: [], motion: [], orientation: [], events: [], layouts: []
            };
            return s;
        },

        // 과제·응답 이벤트 기록. t 를 주면(이벤트의 timeStamp 등) 그 시각으로 기록
        event(type, data, t) {
            if (!s) return;
            s.events.push([rel(t === undefined ? now() : t), type, activeSlide(), data || {}]);
        },

        // 화면이 바뀔 때 호출: 화면 이동 이벤트 + 그 화면의 버튼 배치를 남김
        slide(id) {
            if (!s) return;
            s.events.push([rel(now()), 'slide', id, {}]);
            // 화면 전환 애니메이션(0.4초)이 끝난 뒤의 배치를 잼 (보기 순서 섞기 반영)
            const rec = s.recordId;
            setTimeout(() => { if (s && s.recordId === rec) snapshotLayout(id); }, 450);
        },

        // 세션 시작부터 지금까지의 ms (과제에서 반응시간 계산용)
        t(at) { return rel(at === undefined ? now() : at); },

        active() { return !!s; },

        // 검사를 마칠 때 호출: 저장할 데이터를 돌려줌
        finish(extra) {
            if (!s) return null;
            s.endedAt = new Date().toISOString();
            s.durationMs = rel(now());
            if (extra) s.extra = extra;
            s.counts = { touch: s.touch.length, motion: s.motion.length, orientation: s.orientation.length, events: s.events.length, layouts: s.layouts.length };
            const out = s;
            return out;
        },

        // 다음 검사를 위해 비움
        clear() { s = null; },

        // 개발·확인용
        peek() { return s; }
    };
})();
