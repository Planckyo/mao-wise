import streamlit as st
import pandas as pd
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
            with st.expander(f"方案 {i}"):
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
    "反馈": page_feedback,
}

choice = st.sidebar.radio("页面", list(PAGES.keys()))
PAGES[choice]()

