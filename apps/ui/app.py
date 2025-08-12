# 确保能找到maowise包 - 运行时注入项目根目录
import sys
import pathlib
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st
import pandas as pd
import time
from pathlib import Path
from maowise.utils.config import load_config
from maowise.utils.logger import logger
from maowise.dataflow.ingest import main as ingest_main
from maowise.kb.build_index import build_index
from maowise.kb.search import kb_search
from maowise.models.infer_fwd import predict_performance
from maowise.optimize.engines import recommend_solutions


st.set_page_config(page_title="MAO-Wise", layout="wide")
cfg = load_config()


def page_data_center():
    st.header("数据中心：上传与构建")
    uploaded = st.file_uploader("上传 PDF", type=["pdf"], accept_multiple_files=True)
    if uploaded:
        out_dir = Path(cfg["paths"]["data_raw"]) 
        out_dir.mkdir(parents=True, exist_ok=True)
        for f in uploaded:
            dest = out_dir / f.name
            with open(dest, "wb") as w:
                w.write(f.read())
        st.success(f"已保存 {len(uploaded)} 个 PDF 到 {out_dir}")

    if st.button("运行抽取与建库"):
        stats = ingest_main(cfg["paths"]["data_raw"], f"{cfg['paths']['versions']}/maowise_ds_v1")
        build_index(f"{cfg['paths']['data_parsed']}/corpus.jsonl", cfg["paths"]["index_store"])
        st.json(stats)


def page_predict():
    st.header("性能预测：文本 → α/ε")
    text = st.text_area("输入自由文本（实验方法 + 材料体系）", height=200)
    if st.button("预测") and text.strip():
        res = predict_performance(text, topk_cases=3)
        col1, col2, col3 = st.columns(3)
        col1.metric("α (150–2600nm)", f"{res['alpha']:.3f}")
        col2.metric("ε (3000–30000nm)", f"{res['epsilon']:.3f}")
        col3.metric("置信度", f"{res['confidence']:.2f}")
        
        # 显示解释与引用
        if 'explanation' in res:
            with st.expander("💡 预测解释与文献支撑", expanded=True):
                explanation = res['explanation']
                explanations = explanation.get('explanations', [])
                citation_map = explanation.get('citation_map', {})
                
                st.write("**预测依据:**")
                for j, exp in enumerate(explanations, 1):
                    st.write(f"**{j}.** {exp.get('point', '')}")
                    
                    # 显示引用
                    citations = exp.get('citations', [])
                    if citations:
                        citation_links = []
                        for cit_id in citations:
                            if cit_id in citation_map:
                                cit_info = citation_map[cit_id]
                                citation_links.append(f"[{cit_id}]({cit_info.get('source', 'Unknown')})")
                        st.markdown(f"*引用: {', '.join(citation_links)}*")
                    st.write("")
                
                # 文献详情
                if citation_map:
                    with st.expander("📚 支撑文献详情", expanded=False):
                        for cit_id, cit_info in citation_map.items():
                            st.markdown(f"**[{cit_id}]** {cit_info.get('source', 'Unknown')} (页 {cit_info.get('page', 'N/A')})")
                            st.markdown(f"*{cit_info.get('text', '')[:300]}...*")
                            st.markdown(f"*相关性得分: {cit_info.get('score', 'N/A'):.3f}*")
                            st.write("---")
        
        st.subheader("相似案例")
        st.dataframe(pd.DataFrame(res.get("nearest_cases", [])))


def page_optimize():
    st.header("反向优化：目标 → 建议")
    alpha = st.slider("目标 α", 0.0, 1.0, 0.20, 0.01)
    epsilon = st.slider("目标 ε", 0.0, 1.0, 0.80, 0.01)
    current_hint = st.text_area("当前方案（可选）", height=120)
    c1, c2 = st.columns(2)
    with c1:
        v_lo, v_hi = st.slider("电压范围 (V)", 100, 700, (200, 500))
    with c2:
        t_lo, t_hi = st.slider("时间范围 (min)", 1, 120, (5, 60))
    if st.button("生成建议"):
        res = recommend_solutions(
            target={"alpha": alpha, "epsilon": epsilon},
            current_hint=current_hint or None,
            constraints={"voltage_V": [v_lo, v_hi], "time_min": [t_lo, t_hi]},
            n_solutions=5,
        )
        sols = res.get("solutions", [])
        st.write(f"返回 {len(sols)} 条方案")
        
        for i, s in enumerate(sols, 1):
            with st.expander(f"方案 {i}: {s.get('description', 'N/A')[:50]}...", expanded=i==1):
                # 基本参数显示
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**预期性能:**")
                    st.write(f"- α: {s.get('expected_alpha', 'N/A')}")
                    st.write(f"- ε: {s.get('expected_epsilon', 'N/A')}")
                    st.write(f"- 置信度: {s.get('confidence', 'N/A')}")
                
                with col2:
                    st.write("**关键参数:**")
                    if 'voltage_V' in s:
                        st.write(f"- 电压: {s['voltage_V']} V")
                    if 'current_density_A_dm2' in s:
                        st.write(f"- 电流密度: {s['current_density_A_dm2']} A/dm²")
                    if 'time_min' in s:
                        st.write(f"- 时间: {s['time_min']} min")
                
                # 解释与引用折叠区
                if 'explanation' in s:
                    with st.expander("💡 解释与引用", expanded=False):
                        explanation = s['explanation']
                        explanations = explanation.get('explanations', [])
                        citation_map = explanation.get('citation_map', {})
                        
                        st.write("**专家解释:**")
                        for j, exp in enumerate(explanations, 1):
                            st.write(f"**{j}.** {exp.get('point', '')}")
                            
                            # 显示引用
                            citations = exp.get('citations', [])
                            if citations:
                                citation_links = []
                                for cit_id in citations:
                                    if cit_id in citation_map:
                                        cit_info = citation_map[cit_id]
                                        citation_links.append(f"[{cit_id}]({cit_info.get('source', 'Unknown')})")
                                st.markdown(f"*引用: {', '.join(citation_links)}*")
                            st.write("")
                        
                        # 文献详情
                        if citation_map:
                            with st.expander("📚 引用文献详情", expanded=False):
                                for cit_id, cit_info in citation_map.items():
                                    st.markdown(f"**[{cit_id}]** {cit_info.get('source', 'Unknown')} (页 {cit_info.get('page', 'N/A')})")
                                    st.markdown(f"*{cit_info.get('text', '')[:300]}...*")
                                    st.markdown(f"*相关性得分: {cit_info.get('score', 'N/A'):.3f}*")
                                    st.write("---")
                
                # 工艺卡折叠区
                if 'plan_yaml' in s:
                    with st.expander("📋 可执行工艺卡", expanded=False):
                        yaml_content = s['plan_yaml']
                        
                        # 显示约束检查结果
                        if s.get('hard_constraints_passed', True):
                            st.success("✅ 通过硬约束检查")
                        else:
                            st.error("❌ 未通过硬约束检查，请调整参数")
                        
                        # 显示YAML内容
                        st.code(yaml_content, language='yaml')
                        
                        # 下载按钮
                        st.download_button(
                            label=f"📥 下载方案{i}工艺卡 (.yaml)",
                            data=yaml_content,
                            file_name=f"mao_process_plan_{i}.yaml",
                            mime="text/yaml",
                            help="下载可执行的工艺卡文件"
                        )
                        
                        # 工艺卡引用
                        if 'plan_citations' in s and s['plan_citations']:
                            st.write("**工艺卡文献支撑:**")
                            for cit_id, cit_info in s['plan_citations'].items():
                                st.markdown(f"**[{cit_id}]** {cit_info.get('source', 'Unknown')} (页 {cit_info.get('page', 'N/A')})")
                
                # 原始JSON数据（调试用）
                with st.expander("🔧 原始数据", expanded=False):
                    st.json(s)
        df = pd.DataFrame([
            {"方案": i + 1, "α": s["predicted"]["alpha"], "ε": s["predicted"]["epsilon"]}
            for i, s in enumerate(sols)
        ])
        if not df.empty:
            st.bar_chart(df.set_index("方案"))
        import json as _json
        st.download_button("导出JSON", data=_json.dumps(res, ensure_ascii=False, indent=2), file_name="recommendations.json")


def page_kb():
    st.header("知识检索")
    q = st.text_input("查询")
    if st.button("检索") and q.strip():
        hits = kb_search(q, k=5)
        st.dataframe(pd.DataFrame(hits))


def page_expert_qa():
    st.header("专家问答系统")
    
    # 初始化会话状态
    if "expert_thread" not in st.session_state:
        st.session_state.expert_thread = {
            "questions": [],
            "answers": {},
            "current_question_idx": 0,
            "status": "active",
            "thread_id": f"thread_{int(time.time())}"
        }
    
    thread = st.session_state.expert_thread
    
    # 显示进度
    if thread["questions"]:
        progress = len([q for q in thread["questions"] if thread["answers"].get(q["id"])]) / len(thread["questions"])
        st.progress(progress, text=f"问题进度: {int(progress*100)}%")
    
    # 生成初始问题按钮
    if not thread["questions"]:
        st.info("点击下方按钮开始专家咨询流程")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔍 生成必答问题", type="primary"):
                try:
                    from maowise.experts.clarify import generate_clarify_questions
                    
                    questions = generate_clarify_questions(
                        current_data={},
                        context_description="专家咨询",
                        max_questions=5,
                        include_mandatory=True
                    )
                    
                    thread["questions"] = [q.model_dump() for q in questions]
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"生成问题失败: {e}")
        
        with col2:
            if st.button("📋 查看问题清单"):
                try:
                    from maowise.experts.followups import load_question_catalog
                    catalog = load_question_catalog()
                    mandatory_qs = catalog.get("mandatory_questions", [])
                    
                    st.write("**必答问题清单:**")
                    for i, q in enumerate(mandatory_qs, 1):
                        priority_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(q.get("priority", "medium"), "🟡")
                        st.write(f"{priority_icon} **{i}.** {q['question']}")
                        st.write(f"   *{q['rationale']}*")
                        st.write("")
                        
                except Exception as e:
                    st.error(f"加载问题清单失败: {e}")
        return
    
    # 显示问题和回答
    for i, question in enumerate(thread["questions"]):
        question_id = question["id"]
        
        # 问题标题和标记
        col1, col2, col3 = st.columns([0.7, 0.2, 0.1])
        
        with col1:
            # 优先级和类型标记
            priority_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(question.get("priority", "medium"), "🟡")
            mandatory_mark = "⭐" if question.get("is_mandatory") else ""
            followup_mark = "🔄" if question.get("is_followup") else ""
            
            st.markdown(f"### {priority_icon} {mandatory_mark} {followup_mark} 问题 {i+1}")
            st.write(question["question"])
            st.caption(f"💡 {question.get('rationale', '')}")
        
        with col2:
            # 状态指示
            if question_id in thread["answers"] and thread["answers"][question_id].strip():
                st.success("✅ 已回答")
            else:
                if question.get("is_mandatory"):
                    st.error("❗ 必答")
                else:
                    st.warning("⏳ 待回答")
        
        with col3:
            # 操作按钮
            if question.get("is_followup"):
                st.caption("追问")
        
        # 回答输入区域
        current_answer = thread["answers"].get(question_id, "")
        
        if question.get("kind") == "choice" and question.get("options"):
            # 选择题
            options = question["options"]
            current_idx = 0
            if current_answer in options:
                current_idx = options.index(current_answer)
            
            selected = st.selectbox(
                f"请选择 (问题 {i+1})",
                options,
                index=current_idx,
                key=f"select_{question_id}"
            )
            
            if selected != current_answer:
                thread["answers"][question_id] = selected
                st.rerun()
                
        else:
            # 文本输入
            answer = st.text_area(
                f"请回答 (问题 {i+1})",
                value=current_answer,
                height=100,
                key=f"answer_{question_id}"
            )
            
            if answer != current_answer:
                thread["answers"][question_id] = answer
        
        # 追问逻辑
        if (question_id in thread["answers"] and 
            thread["answers"][question_id].strip() and 
            not question.get("is_followup")):
            
            # 检查是否需要追问
            try:
                from maowise.experts.followups import is_answer_vague, load_question_catalog
                
                catalog = load_question_catalog()
                mandatory_qs = catalog.get("mandatory_questions", [])
                q_config = next((q for q in mandatory_qs if q["id"] == question_id), None)
                
                if q_config and is_answer_vague(thread["answers"][question_id], q_config):
                    col_followup1, col_followup2 = st.columns([0.7, 0.3])
                    
                    with col_followup1:
                        st.warning(f"⚠️ 回答'{thread['answers'][question_id]}'过于含糊")
                    
                    with col_followup2:
                        if st.button(f"🔄 一键追问", key=f"followup_{question_id}"):
                            # 生成追问
                            try:
                                from maowise.experts.clarify import generate_clarify_questions
                                
                                followup_questions = generate_clarify_questions(
                                    current_data={},
                                    expert_answers={question_id: thread["answers"][question_id]},
                                    max_questions=1,
                                    include_mandatory=False
                                )
                                
                                if followup_questions:
                                    # 添加追问到问题列表
                                    new_q = followup_questions[0].model_dump()
                                    thread["questions"].insert(i+1, new_q)
                                    st.rerun()
                                    
                            except Exception as e:
                                st.error(f"生成追问失败: {e}")
                                
            except Exception as e:
                st.caption(f"追问检查失败: {e}")
        
        st.divider()
    
    # 底部操作
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔄 重新生成问题"):
            thread["questions"] = []
            thread["answers"] = {}
            st.rerun()
    
    with col2:
        # 检查完成状态
        answered_count = len([q for q in thread["questions"] if thread["answers"].get(q["id"], "").strip()])
        mandatory_count = len([q for q in thread["questions"] if q.get("is_mandatory")])
        mandatory_answered = len([q for q in thread["questions"] 
                                if q.get("is_mandatory") and thread["answers"].get(q["id"], "").strip()])
        
        if mandatory_answered == mandatory_count and answered_count > 0:
            if st.button("✅ 完成问答并继续", type="primary"):
                thread["status"] = "resolved"
                st.success("✅ 专家问答完成！可以继续进行预测或优化。")
                
                # 显示收集到的信息
                with st.expander("📋 收集到的信息", expanded=True):
                    for question in thread["questions"]:
                        if thread["answers"].get(question["id"], "").strip():
                            st.write(f"**{question['question']}**")
                            st.write(f"回答: {thread['answers'][question['id']]}")
                            st.write("")
        else:
            st.info(f"必答问题进度: {mandatory_answered}/{mandatory_count}")
    
    with col3:
        if st.button("📊 验证回答质量"):
            try:
                from maowise.experts.followups import validate_mandatory_answers
                
                validation = validate_mandatory_answers(thread["answers"])
                
                if validation["all_answered"] and validation["all_specific"]:
                    st.success("✅ 所有回答都符合要求")
                else:
                    if validation["missing_questions"]:
                        st.error(f"❌ {len(validation['missing_questions'])} 个必答问题未回答")
                    
                    if validation["vague_answers"]:
                        st.warning(f"⚠️ {len(validation['vague_answers'])} 个回答过于含糊")
                        
                    if validation["needs_followup"]:
                        st.info(f"🔄 需要 {len(validation['needs_followup'])} 个追问")
                        
            except Exception as e:
                st.error(f"验证失败: {e}")


def page_llm_chat():
    st.header("LLM 聊天助手")
    
    # 配置选项
    col1, col2 = st.columns(2)
    with col1:
        use_rag = st.checkbox("使用 RAG（知识检索增强）", value=True)
    with col2:
        provider = st.selectbox("LLM 提供商", ["local", "openai", "azure"], index=0)
    
    # 系统提示
    system_prompt = st.text_area(
        "系统提示", 
        value="你是微弧氧化研究的专业助手，请基于提供的文献内容回答问题。",
        height=100
    )
    
    # 聊天界面
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # 显示聊天历史
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # 用户输入
    if prompt := st.chat_input("请输入您的问题..."):
        # 添加用户消息
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # 调用 LLM
        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                try:
                    from maowise.llm.client import llm_chat
                    from maowise.llm.rag import build_rag_prompt
                    
                    if use_rag:
                        messages = build_rag_prompt(prompt, system_prompt)
                    else:
                        messages = [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ]
                    
                    response = llm_chat(messages)
                    content = response.get("content", "")
                    usage = response.get("usage", {})
                    
                    st.markdown(content)
                    
                    # 显示使用统计
                    if usage.get("total_tokens", 0) > 0:
                        st.caption(f"Token 使用: {usage.get('total_tokens', 0)} (提示: {usage.get('prompt_tokens', 0)}, 完成: {usage.get('completion_tokens', 0)})")
                    
                    # 添加助手回复到历史
                    st.session_state.messages.append({"role": "assistant", "content": content})
                    
                except Exception as e:
                    error_msg = f"抱歉，处理您的请求时出现错误：{str(e)}"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
    
    # 清除聊天历史按钮
    if st.button("清除聊天历史"):
        st.session_state.messages = []
        st.rerun()


def page_feedback():
    st.header("反馈")
    rating = st.slider("评分", 1, 5, 4)
    note = st.text_area("备注", height=120)
    if st.button("提交"):
        fb_file = Path(cfg["paths"]["versions"]) / "feedback.parquet"
        df = pd.DataFrame([[rating, note]], columns=["rating", "note"])
        if fb_file.exists():
            old = pd.read_parquet(fb_file)
            df = pd.concat([old, df], ignore_index=True)
        df.to_parquet(fb_file, index=False)
        st.success("已记录反馈")


PAGES = {
    "数据中心": page_data_center,
    "性能预测": page_predict,
    "优化建议": page_optimize,
    "知识检索": page_kb,
    "专家问答": page_expert_qa,
    "LLM 聊天": page_llm_chat,
    "反馈": page_feedback,
}

choice = st.sidebar.radio("页面", list(PAGES.keys()))
PAGES[choice]()

