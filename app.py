import streamlit as st
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from openai import OpenAI

# ── 페이지 설정 ─────────────────────────────────────────────
st.set_page_config(
    page_title="정서를 표현하는 글 쓰기",
    page_icon="✍️",
    layout="centered",
)

# ── 스타일 ──────────────────────────────────────────────────
st.markdown("""
<style>
  .step-header {
    background: #1B5E20; color: white;
    padding: 10px 18px; border-radius: 8px;
    font-size: 1.05rem; font-weight: 700;
    margin-bottom: 12px;
  }
  .step-inactive {
    background: #E8F5E9; color: #2E7D32;
    padding: 10px 18px; border-radius: 8px;
    font-size: 1.0rem; font-weight: 600;
    margin-bottom: 6px;
  }
  .tip-box {
    background: #FFFDE7; border-left: 4px solid #F9A825;
    padding: 10px 14px; border-radius: 4px;
    font-size: 0.92rem; margin-bottom: 10px;
  }
  .ai-box {
    background: #E8F5E9; border-left: 4px solid #2E7D32;
    padding: 12px 16px; border-radius: 4px;
    font-size: 0.95rem; margin-top: 12px;
  }
  .api-badge {
    background: #E3F2FD; border: 1px solid #90CAF9;
    padding: 4px 10px; border-radius: 12px;
    font-size: 0.80rem; color: #1565C0;
    display: inline-block; margin-bottom: 8px;
  }
</style>
""", unsafe_allow_html=True)

# ── Gemini API 키 자동 전환 ──────────────────────────────────
def get_api_keys():
    if "GEMINI_API_KEYS" in st.secrets:
        keys = list(st.secrets["GEMINI_API_KEYS"])
        if keys:
            return keys
    keys = []
    i = 1
    while True:
        key_name = f"GEMINI_API_KEY_{i}"
        if key_name in st.secrets:
            keys.append(st.secrets[key_name])
            i += 1
        else:
            break
    if not keys and "GEMINI_API_KEY" in st.secrets:
        return [st.secrets["GEMINI_API_KEY"]]
    return keys

def ai_call(prompt: str):
    """API 키를 순서대로 시도, 성공 시 (응답 텍스트, 사용된 키 번호, 전체 키 수) 반환"""
    keys = get_api_keys()
    last_error = None
    for idx, key in enumerate(keys):
        try:
            client = OpenAI(
                api_key=key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
            resp = client.chat.completions.create(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8192,
                temperature=0.3,
                stream=False,
            )
            return resp.choices[0].message.content, idx + 1, len(keys)
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg:
                last_error = e
                continue
            raise e
    raise Exception(f"모든 API 키의 할당량이 초과되었습니다. 잠시 후 다시 시도해 주세요.\n(마지막 오류: {last_error})")

# ── Google Sheets 연결 ───────────────────────────────────────
@st.cache_resource
def get_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_url(
        "https://docs.google.com/spreadsheets/d/1PGu2WWAtBQNaVLHUE6VP1xb0A-ZZfB1B5LugBZopJsc/edit"
    ).sheet1

HEADERS = ["학번", "이름", "글쓰기 단계", "제출 내용", "피드백 내용", "제출 시각"]

def log_to_sheet(student_id, name, step_name, content, feedback=""):
    import time
    for attempt in range(3):
        try:
            sheet = get_sheet()
            existing = sheet.get_all_values()
            if not existing:
                sheet.append_row(HEADERS)
                time.sleep(0.3)
            sheet.append_row([
                str(student_id), name, step_name, content, feedback,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ])
            return
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                st.warning(f"기록 저장 중 오류가 발생했어요: {e}")

# ── 세션 초기화 ─────────────────────────────────────────────
defaults = {
    "page": "login",        # login → menu → step1~5
    "student_id": "",
    "student_name": "",
    "plan": {},
    "memo": "",
    "structure_paras": [""] * 5,
    "structure": "",
    "structure_fb": "",
    "draft": "",
    "checklist": {},
    "expr_inputs": {},      # 표현 방법별 학생 입력
    "revise_fb": "",
    "api_used": None,       # (사용된 키 번호, 전체 키 수)
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── 헬퍼 ────────────────────────────────────────────────────
def go(page):
    st.session_state.page = page
    st.rerun()

def student_bar():
    sid = st.session_state.student_id
    name = st.session_state.student_name
    if sid or name:
        st.caption(f"👤 {sid}  {name}")

def api_badge():
    if st.session_state.api_used:
        used, total = st.session_state.api_used
        st.markdown(
            f'<div class="api-badge">🔑 API 키 {used} / {total} 사용 중</div>',
            unsafe_allow_html=True
        )

def step_label(n, title, active):
    tag = "step-header" if active else "step-inactive"
    st.markdown(f'<div class="{tag}">STEP {n}  |  {title}</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# PAGE: LOGIN
# ══════════════════════════════════════════════════════════════
if st.session_state.page == "login":
    st.markdown('<div class="step-header">✍️ 정서를 표현하는 글 쓰기</div>',
                unsafe_allow_html=True)
    st.caption("시작하기 전에 학번과 이름을 입력해 주세요.")
    st.markdown("")

    student_id   = st.text_input("학번", placeholder="예) 10101",
                                 value=st.session_state.student_id)
    student_name = st.text_input("이름", placeholder="예) 홍길동",
                                 value=st.session_state.student_name)

    if st.button("시작하기 →", type="primary"):
        if not student_id.strip() or not student_name.strip():
            st.warning("학번과 이름을 모두 입력해 주세요.")
        else:
            st.session_state.student_id   = student_id.strip()
            st.session_state.student_name = student_name.strip()
            go("menu")

# ══════════════════════════════════════════════════════════════
# PAGE: MENU
# ══════════════════════════════════════════════════════════════
elif st.session_state.page == "menu":
    student_bar()
    st.markdown('<div class="step-header">✍️ 글쓰기 단계 선택</div>',
                unsafe_allow_html=True)
    st.caption("진행할 단계를 선택하세요.")
    st.markdown("")

    steps = [
        ("step1", "STEP 1 | 계획하기"),
        ("step2", "STEP 2 | 내용 생성하기"),
        ("step3", "STEP 3 | 내용 조직하기  ✦ AI 피드백"),
        ("step4", "STEP 4 | 초고 쓰기"),
        ("step5", "STEP 5 | 고쳐쓰기  ✦ AI 피드백"),
    ]
    for page_key, label in steps:
        if st.button(label, use_container_width=True):
            go(page_key)

    st.divider()
    if st.button("← 학번·이름 변경"):
        go("login")

# ══════════════════════════════════════════════════════════════
# PAGE: STEP 1 · 계획하기
# ══════════════════════════════════════════════════════════════
elif st.session_state.page == "step1":
    student_bar()
    step_label(1, "계획하기", True)
    st.caption("글을 쓰기 전, 무엇을 어떻게 쓸지 계획해 봅시다.")

    st.markdown('<div class="tip-box">💡 사소한 경험이어도 괜찮습니다. '
                '나에게 <b>의미 있었던</b> 순간이면 충분합니다.</div>',
                unsafe_allow_html=True)

    glam = st.text_area("① 글감 (어떤 경험을 쓸 건가요?)",
                        value=st.session_state.plan.get("glam", ""),
                        placeholder="예) 엘리베이터 공사로 계단을 오르내리다 옆집 할머니를 도운 일",
                        height=80)
    emotion = st.text_input("② 중심 정서 (그때 가장 크게 느낀 감정)",
                            value=st.session_state.plan.get("emotion", ""),
                            placeholder="예) 처음엔 짜증스러웠지만, 도와드린 뒤 뿌듯했다")
    method = st.multiselect("③ 활용할 표현 방법 (하나 이상 선택)",
                            ["운율", "비유", "상징"],
                            default=st.session_state.plan.get("method", []))

    col1, col2, col3 = st.columns([1, 3, 1])
    with col1:
        if st.button("← 메뉴"):
            go("menu")
    with col3:
        if st.button("저장하기 ✓", type="primary", use_container_width=True):
            if not glam.strip() or not emotion.strip() or not method:
                st.warning("세 항목을 모두 입력해 주세요.")
            else:
                st.session_state.plan = {"glam": glam, "emotion": emotion, "method": method}
                content = f"글감: {glam}\n중심 정서: {emotion}\n표현 방법: {', '.join(method)}"
                log_to_sheet(st.session_state.student_id, st.session_state.student_name,
                             "① 계획하기", content)
                st.success("저장되었습니다! 메뉴로 돌아가 다음 단계를 선택하세요.")

# ══════════════════════════════════════════════════════════════
# PAGE: STEP 2 · 내용 생성하기
# ══════════════════════════════════════════════════════════════
elif st.session_state.page == "step2":
    student_bar()
    step_label(2, "내용 생성하기", True)
    st.caption("경험을 자유롭게 떠올려 메모해 봅시다. 형식은 신경 쓰지 않아도 됩니다.")

    p = st.session_state.plan
    if p:
        st.info(f"📌 글감: {p.get('glam','')}  |  중심 정서: {p.get('emotion','')}  |  표현 방법: {', '.join(p.get('method',[]))}")

    st.markdown('<div class="tip-box">💡 생각나는 장면, 대화, 감정, 색깔, 소리 등 '
                '떠오르는 것을 모두 적어보세요. 양이 많을수록 좋습니다.</div>',
                unsafe_allow_html=True)

    memo = st.text_area("자유 메모",
                        value=st.session_state.memo,
                        placeholder="예)\n- 176개 계단, 숨이 턱까지 차오름\n- 할머니 흰 머리카락, 힘겨운 한숨 소리\n- 돕고 싶은데 학원 늦을까봐 망설임",
                        height=220)

    col1, col2, col3 = st.columns([1, 3, 1])
    with col1:
        if st.button("← 메뉴"):
            go("menu")
    with col3:
        if st.button("저장하기 ✓", type="primary", use_container_width=True):
            if len(memo.strip()) < 20:
                st.warning("조금 더 자세히 메모해 주세요.")
            else:
                st.session_state.memo = memo
                log_to_sheet(st.session_state.student_id, st.session_state.student_name,
                             "② 내용 생성하기", memo)
                st.success("저장되었습니다! 메뉴로 돌아가 다음 단계를 선택하세요.")

# ══════════════════════════════════════════════════════════════
# PAGE: STEP 3 · 내용 조직하기  ★ AI 개입
# ══════════════════════════════════════════════════════════════
elif st.session_state.page == "step3":
    student_bar()
    step_label(3, "내용 조직하기  ✦ AI 피드백", True)
    st.caption("메모한 내용을 글의 순서대로 정리해 봅시다.")

    p = st.session_state.plan
    if p:
        st.info(f"📌 중심 정서: {p.get('emotion','')}")

    st.markdown('<div class="tip-box">💡 각 문단에 <b>일어난 일</b>과 <b>그때 느낀 감정</b>을 함께 써 보세요. '
                '처음(시작) → 중간1 → 중간2 → 중간3 → 끝(결말·깨달음) 순서로 구성합니다.</div>',
                unsafe_allow_html=True)

    para_labels = [
        ("1문단", "처음 (시작 장면·상황)"),
        ("2문단", "중간1 (사건 전개)"),
        ("3문단", "중간2 (변화·갈등)"),
        ("4문단", "중간3 (전환·결심)"),
        ("5문단", "끝 (결말·깨달음)"),
    ]

    paras = []
    for i, (num, hint) in enumerate(para_labels):
        val = st.text_area(
            f"**{num}** — {hint}",
            value=st.session_state.structure_paras[i],
            height=90,
            key=f"para_{i}"
        )
        paras.append(val)
    st.session_state.structure_paras = paras

    structure = "\n".join(
        f"{label[0]}: {p_}" for label, p_ in zip(para_labels, paras) if p_.strip()
    )
    all_filled = all(p_.strip() for p_ in paras)

    api_badge()
    if st.button("🤖 AI 피드백 받기", type="primary", disabled=not all_filled):
        with st.spinner("AI가 구성을 분석하고 있습니다..."):
            plan = st.session_state.plan
            prompt = f"""당신은 중학교 1학년 국어 글쓰기를 지도하는 교사입니다.
학생이 '정서를 표현하는 글 쓰기' 수행평가를 위해 글의 구성을 작성하였습니다.
친절하지만 사실에 기반한 솔직하고 단호한 피드백을 '--습니다'체로 제공하십시오.
정답을 직접 알려주지 말고, 학습자가 스스로 생각하고 해결할 수 있도록 비계를 제공하십시오.

[학생 정보]
- 글감: {plan.get('glam','')}
- 중심 정서: {plan.get('emotion','')}
- 활용할 표현 방법: {', '.join(plan.get('method',[]))}
- 자유 메모: {st.session_state.memo}

[학생이 작성한 글의 구성]
{structure}

[피드백 지침]
반드시 아래 두 파트로만 구성하십시오.

**[구성 평가]**
- 중심 정서({plan.get('emotion','')})가 각 문단에서 잘 드러나는지 구체적으로 평가하십시오.
- 문단 간 흐름이 자연스러운지, 어색한 부분이 있다면 어느 문단인지 명확히 지적하십시오.
- 막연한 칭찬은 하지 말고, 실제로 잘된 부분이 있을 때만 한 문장 언급하십시오.

**[스스로 점검할 질문]**
- 학생이 구성을 스스로 고칠 수 있도록 구체적인 방향을 담은 질문 2개를 제시하십시오.
- 단순한 "잘 되었나요?" 형태가 아닌, 무엇을 어떻게 고쳐야 할지 생각하게 만드는 질문이어야 합니다.
- 답을 직접 알려주지 말고, 스스로 생각하게 열어두십시오."""

            fb, key_used, key_total = ai_call(prompt)
            st.session_state.structure_fb = fb
            st.session_state.api_used = (key_used, key_total)
            log_to_sheet(st.session_state.student_id, st.session_state.student_name,
                         "③ 내용 조직하기", structure, fb)

    api_badge()
    if st.session_state.structure_fb:
        st.markdown(f'<div class="ai-box">🤖 <b>AI 피드백</b><br><br>'
                    f'{st.session_state.structure_fb.replace(chr(10), "<br>")}</div>',
                    unsafe_allow_html=True)

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("← 메뉴"):
            st.session_state.structure = structure
            go("menu")
    with col2:
        if st.button("저장하고 메뉴로 →", type="primary"):
            if not structure.strip():
                st.warning("구성을 먼저 작성해 주세요.")
            else:
                st.session_state.structure = structure
                st.success("저장되었습니다! 메뉴로 돌아가 다음 단계를 선택하세요.")

# ══════════════════════════════════════════════════════════════
# PAGE: STEP 4 · 초고 쓰기
# ══════════════════════════════════════════════════════════════
elif st.session_state.page == "step4":
    student_bar()
    step_label(4, "초고 쓰기", True)
    st.caption("조직한 내용을 바탕으로 글을 써 봅시다.")

    p = st.session_state.plan
    if p:
        st.info(f"📌 중심 정서: {p.get('emotion','')}  |  표현 방법: {', '.join(p.get('method',[]))}")

    st.markdown('<div class="tip-box">💡 맞춤법이나 문장이 완벽하지 않아도 됩니다. '
                '지금은 내 생각과 감정을 글로 꺼내는 것이 가장 중요합니다. '
                '<b>200자 이상 400자 이내</b>로 써 보세요.</div>',
                unsafe_allow_html=True)

    title = st.text_input("제목", placeholder="글의 제목을 입력하세요",
                          value=st.session_state.plan.get("title", ""))
    draft = st.text_area("초고",
                         value=st.session_state.draft,
                         placeholder="여기에 글을 써 주세요...",
                         height=320)

    char_count = len(draft.replace(" ", "").replace("\n", ""))
    st.caption(f"현재 글자 수 (공백·줄바꿈 제외): {char_count}자")
    if char_count > 0 and char_count < 200:
        st.warning(f"200자 이상 써주세요. (현재 {char_count}자)")
    elif char_count > 400:
        st.warning(f"400자 이내로 줄여주세요. (현재 {char_count}자)")

    col1, col2, col3 = st.columns([1, 3, 1])
    with col1:
        if st.button("← 메뉴"):
            go("menu")
    with col3:
        if st.button("저장하기 ✓", type="primary", use_container_width=True):
            if char_count < 200:
                st.warning("200자 이상 써야 저장할 수 있습니다.")
            elif not title.strip():
                st.warning("제목을 입력해 주세요.")
            else:
                st.session_state.draft = draft
                st.session_state.plan["title"] = title
                content = f"제목: {title}\n\n{draft}"
                log_to_sheet(st.session_state.student_id, st.session_state.student_name,
                             "④ 초고 쓰기", content)
                st.success("저장되었습니다! 메뉴로 돌아가 다음 단계를 선택하세요.")

# ══════════════════════════════════════════════════════════════
# PAGE: STEP 5 · 고쳐쓰기  ★ AI 개입 (표현 방법 중심)
# ══════════════════════════════════════════════════════════════
elif st.session_state.page == "step5":
    student_bar()
    step_label(5, "고쳐쓰기  ✦ AI 피드백", True)
    st.caption("초고에서 활용한 표현 방법을 점검하고, AI 피드백을 받아 봅시다.")

    plan = st.session_state.plan
    methods = plan.get("method", [])

    with st.expander("📄 내 초고 보기", expanded=False):
        st.markdown(f"**{plan.get('title', '')}**")
        st.write(st.session_state.draft)

    st.divider()

    # ── 자기 점검 체크리스트 ──────────────────────────────
    st.markdown("#### 📋 자기 점검 체크리스트")
    st.caption("먼저 스스로 점검한 뒤, AI 피드백을 받으세요.")

    checks = {
        "c1": "특정 경험이나 장면이 구체적으로 드러나 있다.",
        "c2": "막연한 감정어 대신 상황과 연결된 감정을 표현하였다.",
        "c3": "운율·비유·상징 중 하나 이상을 의도적으로 활용하였다.",
        "c4": "중심 정서가 글의 처음부터 끝까지 일관되게 유지된다.",
        "c5": "글의 처음과 끝이 자연스럽게 연결된다.",
    }
    check_results = {}
    for key, label in checks.items():
        check_results[key] = st.checkbox(label, value=st.session_state.checklist.get(key, False))
    st.session_state.checklist = check_results

    st.divider()

    # ── 표현 방법별 입력 ─────────────────────────────────
    st.markdown("#### ✏️ 활용한 표현 방법 입력")
    st.caption("초고에서 해당 표현 방법을 활용한 부분을 직접 입력하세요.")

    expr_inputs = st.session_state.expr_inputs

    if "운율" in methods:
        st.markdown("**운율**")
        st.markdown('<div class="tip-box">💡 운율: 글에서 소리나 리듬이 반복되는 부분입니다. '
                    '비슷한 어미, 음절 수, 반복되는 표현 등을 찾아보세요.</div>',
                    unsafe_allow_html=True)
        expr_inputs["운율"] = st.text_area(
            "운율이 나타난 부분을 초고에서 찾아 그대로 입력하세요.",
            value=expr_inputs.get("운율", ""),
            height=80, key="expr_운율"
        )

    if "비유" in methods:
        st.markdown("**비유**")
        st.markdown('<div class="tip-box">💡 비유: <b>구체적인 대상(원관념)</b>을 '
                    '<b>다른 구체적인 대상(보조 관념)</b>에 빗대어 표현하는 방법입니다. '
                    '(예: "다리가 납덩이처럼 무거웠다" → 원관념: 다리, 보조 관념: 납덩이)</div>',
                    unsafe_allow_html=True)
        expr_inputs["비유_문장"] = st.text_area(
            "비유가 사용된 문장을 초고에서 찾아 그대로 입력하세요.",
            value=expr_inputs.get("비유_문장", ""),
            height=80, key="expr_비유_문장"
        )
        col_a, col_b = st.columns(2)
        with col_a:
            expr_inputs["비유_원관념"] = st.text_input(
                "원관념 (실제로 표현하려는 구체적 대상)",
                value=expr_inputs.get("비유_원관념", ""),
                key="expr_비유_원"
            )
        with col_b:
            expr_inputs["비유_보조관념"] = st.text_input(
                "보조 관념 (빗댄 구체적 대상)",
                value=expr_inputs.get("비유_보조관념", ""),
                key="expr_비유_보조"
            )

    if "상징" in methods:
        st.markdown("**상징**")
        st.markdown('<div class="tip-box">💡 상징: <b>추상적인 개념(원관념)</b>을 '
                    '<b>구체적인 대상(보조 관념)</b>으로 나타내는 방법입니다. '
                    '(예: "176개의 계단이 선물처럼 느껴졌다" → 원관념: 힘든 상황·성장, 보조 관념: 계단)</div>',
                    unsafe_allow_html=True)
        expr_inputs["상징_문장"] = st.text_area(
            "상징이 사용된 문장을 초고에서 찾아 그대로 입력하세요.",
            value=expr_inputs.get("상징_문장", ""),
            height=80, key="expr_상징_문장"
        )
        col_a, col_b = st.columns(2)
        with col_a:
            expr_inputs["상징_원관념"] = st.text_input(
                "원관념 (상징하려는 추상적 개념)",
                value=expr_inputs.get("상징_원관념", ""),
                key="expr_상징_원"
            )
        with col_b:
            expr_inputs["상징_보조관념"] = st.text_input(
                "보조 관념 (상징하는 구체적 대상)",
                value=expr_inputs.get("상징_보조관념", ""),
                key="expr_상징_보조"
            )

    st.session_state.expr_inputs = expr_inputs

    st.divider()

    # ── AI 피드백 ─────────────────────────────────────────
    st.markdown("#### 🤖 AI 표현 방법 점검")

    api_badge()
    if st.button("AI 피드백 받기", type="primary"):
        with st.spinner("AI가 표현 방법을 분석하고 있습니다..."):

            # 표현 방법 입력 정리
            expr_summary = []
            if "운율" in methods:
                expr_summary.append(f"[운율] 학생이 찾은 부분: {expr_inputs.get('운율','(미입력)')}")
            if "비유" in methods:
                expr_summary.append(
                    f"[비유] 사용 문장: {expr_inputs.get('비유_문장','(미입력)')}\n"
                    f"  원관념: {expr_inputs.get('비유_원관념','(미입력)')} / "
                    f"보조 관념: {expr_inputs.get('비유_보조관념','(미입력)')}"
                )
            if "상징" in methods:
                expr_summary.append(
                    f"[상징] 사용 문장: {expr_inputs.get('상징_문장','(미입력)')}\n"
                    f"  원관념: {expr_inputs.get('상징_원관념','(미입력)')} / "
                    f"보조 관념: {expr_inputs.get('상징_보조관념','(미입력)')}"
                )
            expr_text = "\n".join(expr_summary) if expr_summary else "(표현 방법 입력 없음)"

            unchecked = [label for key, label in checks.items() if not check_results[key]]
            checklist_summary = ("모든 항목을 체크하였습니다." if not unchecked
                                 else f"미체크 항목: {', '.join(unchecked)}")

            prompt = f"""당신은 중학교 1학년 국어 글쓰기를 지도하는 교사입니다.
학생이 초고에서 활용한 표현 방법(운율·비유·상징)을 점검하고 피드백을 제공하십시오.
반드시 '--습니다'체를 사용하고, 친절하지만 객관적이고 단호하게 서술하십시오.
정답을 직접 제공하지 말고, 학습자가 스스로 생각하고 수정할 수 있도록 비계를 제공하십시오.

[개념 정의]
- 비유: 구체적인 대상(원관념)을 다른 구체적인 대상(보조 관념)에 빗대어 표현하는 방법
- 상징: 추상적인 개념(원관념)을 구체적인 대상(보조 관념)으로 나타내는 방법
- 운율: 소리나 리듬이 규칙적으로 반복되는 특성

[학생 초고]
제목: {plan.get('title','')}
{st.session_state.draft}

[학생이 계획한 표현 방법]
{', '.join(methods)}

[학생이 입력한 표현 방법 활용 내용]
{expr_text}

[자기 점검 결과]
{checklist_summary}

[피드백 지침]
반드시 아래 두 파트로만 구성하십시오.

**[표현 방법 평가]**
각 표현 방법에 대해 아래를 평가하십시오.
- 학생이 찾은 원관념과 보조 관념이 개념 정의에 부합하는지 판단하십시오.
- 부합하지 않는다면 어떤 점이 잘못되었는지 구체적으로 지적하십시오.
- 초고에서 해당 표현 방법이 실제로 효과적으로 기능하는지 평가하십시오.
- 표현 방법이 초고에 전혀 나타나지 않는 경우 명확히 지적하십시오.

**[고쳐쓰기 미션]**
- 학생이 스스로 수정 방향을 찾을 수 있도록 구체적인 질문 형태로 안내하십시오.
- 수정된 문장을 직접 제공하지 마십시오.
- 표현 방법이 모두 적절하게 사용된 경우, 더 발전시킬 수 있는 방향을 질문으로 제시하십시오."""

            fb, key_used, key_total = ai_call(prompt)
            st.session_state.revise_fb = fb
            st.session_state.api_used = (key_used, key_total)

            checked_items = [label for key, label in checks.items() if check_results[key]]
            content = (
                f"[자기 점검 완료 항목]\n" +
                "\n".join(f"✓ {c}" for c in checked_items) +
                f"\n\n[표현 방법 입력]\n{expr_text}" +
                f"\n\n[초고]\n제목: {plan.get('title','')}\n{st.session_state.draft}"
            )
            log_to_sheet(st.session_state.student_id, st.session_state.student_name,
                         "⑤ 고쳐쓰기", content, fb)

    api_badge()
    if st.session_state.revise_fb:
        st.markdown(f'<div class="ai-box">🤖 <b>AI 피드백</b><br><br>'
                    f'{st.session_state.revise_fb.replace(chr(10), "<br>")}</div>',
                    unsafe_allow_html=True)

    st.divider()
    st.markdown("#### ✍️ 최종 수정본")
    st.caption("AI 피드백을 반영하여 글을 고쳐 쓰세요.")
    final = st.text_area("최종 수정본",
                         value=st.session_state.draft,
                         height=300)

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("← 메뉴"):
            go("menu")
    with col2:
        if st.button("✅ 최종 제출", type="primary"):
            log_to_sheet(st.session_state.student_id, st.session_state.student_name,
                         "✅ 최종 제출",
                         f"제목: {plan.get('title','')}\n\n{final}")
            st.session_state.final = final
            go("done")

# ══════════════════════════════════════════════════════════════
# PAGE: DONE
# ══════════════════════════════════════════════════════════════
elif st.session_state.page == "done":
    st.balloons()
    st.success("✅ 글쓰기를 모두 마쳤습니다. 수고하였습니다.")

    p = st.session_state.plan
    st.markdown(f"### {p.get('title', '나의 글')}")
    st.write(st.session_state.get("final", st.session_state.draft))

    st.divider()
    st.markdown("**📊 나의 글쓰기 과정 요약**")
    st.markdown(f"- 글감: {p.get('glam', '')}")
    st.markdown(f"- 중심 정서: {p.get('emotion', '')}")
    st.markdown(f"- 활용한 표현 방법: {', '.join(p.get('method', []))}")
    checked = sum(1 for v in st.session_state.checklist.values() if v)
    st.markdown(f"- 자기 점검: {checked}/5 항목 완료")
