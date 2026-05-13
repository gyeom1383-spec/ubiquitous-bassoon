import streamlit as st
import google.generativeai as genai

# ── 페이지 설정 ─────────────────────────────────────────────
st.set_page_config(
    page_title="정서를 표현하는 글 쓰기",
    page_icon="✍️",
    layout="centered",
)

# ── API 설정 ────────────────────────────────────────────────
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-1.5-flash")

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
</style>
""", unsafe_allow_html=True)

# ── 세션 초기화 ─────────────────────────────────────────────
defaults = {
    "step": 1,
    "plan": {},
    "memo": "",
    "structure": "",
    "structure_fb": "",
    "draft": "",
    "checklist": {},
    "revise_fb": "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── 헬퍼 ────────────────────────────────────────────────────
def go(step):
    st.session_state.step = step
    st.rerun()

def ai_call(prompt: str) -> str:
    resp = model.generate_content(prompt)
    return resp.text

def step_label(n, title, active):
    tag = "step-header" if active else "step-inactive"
    st.markdown(f'<div class="{tag}">STEP {n} &nbsp;|&nbsp; {title}</div>',
                unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# STEP 1 · 계획하기
# ══════════════════════════════════════════════════════════════
if st.session_state.step == 1:
    step_label(1, "계획하기", True)
    st.caption("글을 쓰기 전, 무엇을 어떻게 쓸지 계획해 봅시다.")

    st.markdown('<div class="tip-box">💡 사소한 경험이어도 괜찮아요. '
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

    if st.button("다음 단계로 →", type="primary"):
        if not glam.strip() or not emotion.strip() or not method:
            st.warning("세 항목을 모두 입력해 주세요.")
        else:
            st.session_state.plan = {"glam": glam, "emotion": emotion, "method": method}
            go(2)

# ══════════════════════════════════════════════════════════════
# STEP 2 · 내용 생성하기
# ══════════════════════════════════════════════════════════════
elif st.session_state.step == 2:
    step_label(1, "계획하기", False)
    step_label(2, "내용 생성하기", True)
    st.caption("경험을 자유롭게 떠올려 메모해 봅시다. 형식은 신경 쓰지 않아도 돼요.")

    p = st.session_state.plan
    st.info(f"📌 글감: {p['glam']}  |  중심 정서: {p['emotion']}  |  표현 방법: {', '.join(p['method'])}")

    st.markdown('<div class="tip-box">💡 생각나는 장면, 대화, 감정, 색깔, 소리 등 '
                '떠오르는 것을 모두 적어보세요. 양이 많을수록 좋아요!</div>',
                unsafe_allow_html=True)

    memo = st.text_area("자유 메모",
                        value=st.session_state.memo,
                        placeholder="예)\n- 176개 계단, 숨이 턱까지 차오름\n- 체육복 소매가 자전거에 걸려 찢어짐\n- 할머니 흰 머리카락, 힘겨운 한숨 소리\n- 돕고 싶은데 학원 늦을까봐 망설임\n- 짐 들어드리는 순간 마음이 가벼워짐",
                        height=220)

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("← 이전"):
            go(1)
    with col2:
        if st.button("다음 단계로 →", type="primary"):
            if len(memo.strip()) < 20:
                st.warning("조금 더 자세히 메모해 주세요.")
            else:
                st.session_state.memo = memo
                go(3)

# ══════════════════════════════════════════════════════════════
# STEP 3 · 내용 조직하기  ★ AI 개입
# ══════════════════════════════════════════════════════════════
elif st.session_state.step == 3:
    step_label(1, "계획하기", False)
    step_label(2, "내용 생성하기", False)
    step_label(3, "내용 조직하기 ✦ AI 피드백", True)
    st.caption("메모한 내용을 글의 순서대로 정리해 봅시다.")

    p = st.session_state.plan
    st.info(f"📌 중심 정서: {p['emotion']}")

    st.markdown('<div class="tip-box">💡 처음(시작) → 중간(사건·변화) → 끝(결말·깨달음) '
                '순서로 장면이나 문단을 번호 붙여 나열해 보세요.</div>',
                unsafe_allow_html=True)

    structure = st.text_area("장면·문단 순서 나열",
                              value=st.session_state.structure,
                              placeholder="예)\n1. 엘리베이터 공사로 계단 오르내리기 시작 — 힘들고 짜증스러운 마음\n2. 자전거에 소매가 걸려 체육복이 찢어짐 — 불길한 기분\n3. 학원 가는 길, 할머니와 마주침 — 안쓰럽지만 모른 척하고 싶은 마음\n4. 고민 끝에 짐을 들어드리기로 결심\n5. 계단을 함께 오르며 마음이 가벼워짐 — 뿌듯함",
                              height=200)

    # AI 피드백 버튼
    if st.button("🤖 AI 피드백 받기", type="primary", disabled=not structure.strip()):
        with st.spinner("AI가 구성을 분석하고 있어요..."):
            prompt = f"""당신은 중학교 1학년 국어 글쓰기를 돕는 친절한 교사입니다.
학생이 '정서를 표현하는 글 쓰기' 수행평가를 위해 글의 구성을 짰습니다.

[학생 정보]
- 글감: {p['glam']}
- 중심 정서: {p['emotion']}
- 활용할 표현 방법: {', '.join(p['method'])}
- 자유 메모: {st.session_state.memo}

[학생이 짠 글의 구성·순서]
{structure}

[피드백 지침]
반드시 아래 두 파트로만 구성하세요.

**[생각해볼 질문]**
학생이 스스로 구성을 점검할 수 있도록 질문 2개를 제시하세요.
- 중심 정서가 흐름 안에서 자연스럽게 드러나는지 생각하게 유도
- 처음과 끝이 같은 정서적 흐름 안에 있는지 확인하게 유도
- 질문은 답을 직접 알려주지 말고, 스스로 생각하게 열어두세요.

**[구성 제안]**
현재 구성에서 구체적으로 개선할 수 있는 점 1~2가지를 제안하세요.
- 순서 조정이 필요한 부분이 있다면 구체적으로 언급
- 중심 정서 전달에 더 효과적인 방향 제안
- 잘된 점도 한 문장 언급
- 중학교 1학년 눈높이의 친절한 말투로

총 150자 내외로 간결하게 작성하세요."""
            fb = ai_call(prompt)
            st.session_state.structure_fb = fb

    # 피드백 출력
    if st.session_state.structure_fb:
        st.markdown(f'<div class="ai-box">🤖 <b>AI 피드백</b><br><br>'
                    f'{st.session_state.structure_fb.replace(chr(10), "<br>")}</div>',
                    unsafe_allow_html=True)

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("← 이전"):
            go(2)
    with col2:
        if st.button("다음 단계로 →", type="primary"):
            if not structure.strip():
                st.warning("구성을 먼저 작성해 주세요.")
            else:
                st.session_state.structure = structure
                go(4)

# ══════════════════════════════════════════════════════════════
# STEP 4 · 초고 쓰기
# ══════════════════════════════════════════════════════════════
elif st.session_state.step == 4:
    step_label(1, "계획하기", False)
    step_label(2, "내용 생성하기", False)
    step_label(3, "내용 조직하기", False)
    step_label(4, "초고 쓰기", True)
    st.caption("조직한 내용을 바탕으로 글을 써 봅시다.")

    p = st.session_state.plan
    st.info(f"📌 중심 정서: {p['emotion']}  |  표현 방법: {', '.join(p['method'])}")

    st.markdown('<div class="tip-box">💡 맞춤법이나 문장이 완벽하지 않아도 괜찮아요. '
                '지금은 내 생각과 감정을 글로 꺼내는 것이 가장 중요해요. '
                '<b>200자 이상 400자 이내</b>로 써보세요.</div>',
                unsafe_allow_html=True)

    title = st.text_input("제목", value="", placeholder="글의 제목을 입력하세요")
    draft = st.text_area("초고",
                         value=st.session_state.draft,
                         placeholder="여기에 글을 써 주세요...",
                         height=320)

    char_count = len(draft.replace(" ", "").replace("\n", ""))
    st.caption(f"현재 글자 수 (공백·줄바꿈 제외): {char_count}자")
    if char_count < 200:
        st.warning(f"200자 이상 써주세요. (현재 {char_count}자)")
    elif char_count > 400:
        st.warning(f"400자 이내로 줄여주세요. (현재 {char_count}자)")

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("← 이전"):
            go(3)
    with col2:
        if st.button("다음 단계로 →", type="primary"):
            if char_count < 200:
                st.warning("200자 이상 써야 다음 단계로 넘어갈 수 있어요.")
            elif not title.strip():
                st.warning("제목을 입력해 주세요.")
            else:
                st.session_state.draft = draft
                st.session_state.plan["title"] = title
                go(5)

# ══════════════════════════════════════════════════════════════
# STEP 5 · 고쳐쓰기  ★ AI 개입
# ══════════════════════════════════════════════════════════════
elif st.session_state.step == 5:
    step_label(1, "계획하기", False)
    step_label(2, "내용 생성하기", False)
    step_label(3, "내용 조직하기", False)
    step_label(4, "초고 쓰기", False)
    step_label(5, "고쳐쓰기 ✦ AI 피드백", True)
    st.caption("내 글을 스스로 점검하고, AI의 도움을 받아 다듬어 봅시다.")

    # 초고 표시
    with st.expander("📄 내 초고 보기", expanded=False):
        st.markdown(f"**{st.session_state.plan.get('title', '')}**")
        st.write(st.session_state.draft)

    st.divider()

    # 자기 점검 체크리스트
    st.markdown("#### 📋 자기 점검 체크리스트")
    st.caption("먼저 스스로 점검해 본 뒤, AI 피드백을 받으세요.")

    checks = {
        "c1": "특정 경험이나 장면이 구체적으로 드러나 있다.",
        "c2": "'슬프다', '좋다' 같은 막연한 감정어 대신 상황과 연결된 감정을 표현했다.",
        "c3": "운율·비유·상징 중 하나 이상을 의도적으로 활용했다.",
        "c4": "중심 정서가 글의 처음부터 끝까지 일관되게 유지된다.",
        "c5": "글의 처음과 끝이 자연스럽게 연결된다.",
    }

    check_results = {}
    for key, label in checks.items():
        check_results[key] = st.checkbox(label, value=st.session_state.checklist.get(key, False))
    st.session_state.checklist = check_results

    st.divider()

    # AI 피드백
    st.markdown("#### 🤖 AI 표현·문장 점검")
    if st.button("AI 피드백 받기", type="primary"):
        with st.spinner("AI가 문장을 꼼꼼히 살펴보고 있어요..."):
            unchecked = [label for key, label in checks.items() if not check_results[key]]
            checklist_summary = ("모든 항목을 체크했습니다." if not unchecked
                                 else f"아직 점검이 필요한 항목: {', '.join(unchecked)}")

            prompt = f"""당신은 중학교 1학년 국어 글쓰기를 돕는 친절한 교사입니다.
학생이 '정서를 표현하는 글 쓰기' 수행평가 초고를 완성했습니다.
표현과 문장 수준의 피드백만 제공해 주세요. 내용·구성은 다루지 마세요.

[학생 글]
제목: {st.session_state.plan.get('title', '')}
{st.session_state.draft}

[자기 점검 결과]
{checklist_summary}

[피드백 지침]
반드시 아래 두 파트로만 구성하세요.

**[표현 평가]**
- 맞춤법 오류가 있으면 구체적으로 지적 (예: '됬다' → '됐다')
- 어색하거나 반복되는 문장이 있으면 해당 문장을 인용하여 지적
- 없으면 "표현과 문장이 전반적으로 자연스럽습니다."라고만 쓰세요.
- 최대 3가지까지만

**[고쳐쓰기 제안]**
- 위에서 지적한 항목을 어떻게 고치면 좋은지 구체적 예시 제시
- 없으면 "수정 없이 제출해도 좋을 것 같아요!"라고만 쓰세요.
- 중학교 1학년 눈높이의 친절하고 격려하는 말투로
- 총 200자 내외

절대로 글의 내용을 대신 써주거나, 내용 전체를 바꾸는 제안은 하지 마세요."""

            fb = ai_call(prompt)
            st.session_state.revise_fb = fb

    if st.session_state.revise_fb:
        st.markdown(f'<div class="ai-box">🤖 <b>AI 피드백</b><br><br>'
                    f'{st.session_state.revise_fb.replace(chr(10), "<br>")}</div>',
                    unsafe_allow_html=True)

    st.divider()

    # 최종 수정본 제출
    st.markdown("#### ✍️ 최종 수정본")
    final = st.text_area("AI 피드백을 반영해 글을 고쳐 쓰세요.",
                         value=st.session_state.draft,
                         height=300)

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("← 이전"):
            go(4)
    with col2:
        if st.button("✅ 최종 제출", type="primary"):
            st.session_state.final = final
            go(6)

# ══════════════════════════════════════════════════════════════
# STEP 6 · 완료
# ══════════════════════════════════════════════════════════════
elif st.session_state.step == 6:
    st.balloons()
    st.success("✅ 글쓰기를 모두 마쳤어요! 수고했습니다.")

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

    if st.button("처음부터 다시 쓰기"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()
