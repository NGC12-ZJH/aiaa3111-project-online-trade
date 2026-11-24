"""Summarize the four follow-up analyses without reading Test."""
from pathlib import Path
import pandas as pd

OUT = Path(__file__).resolve().parent / "results"
LABEL = {"G": "原 G", "G_greedy": "G 贪心", "rfm": "纯 RFM",
         "rfm_form": "RFM＋采购形态", "form": "纯采购形态"}


def show(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"]*len(headers)) + " |",
                      *["| " + " | ".join(map(str,row)) + " |" for row in rows]])


def read(name):
    return pd.read_csv(OUT/f"{name}.csv")


def pct(x):
    return f"{100*x:.2f}%"


def main():
    distinct=read("distinct_summary")
    block=distinct.query("metric=='rest_bc' and control=='B2'").set_index(["variant","length","period"])
    rows=[]
    for m in ("rfm","rfm_form","form"):
        for k in (2,3):
            a,b=(block.loc[m,k,p] for p in ("discovery","validation"))
            cells=[]
            for x in (a,b):
                cells += [f"{x.real:.3f}",f"{x['median']:.3f}",f"{x.gap:+.3f}",f"{int(x.random_ge)}/100"]
            rows.append((LABEL[m],k,*cells))
    txt=["# 1123 四项补测结果", "使用 Profile、Discovery 与 Validation。固定 P5／120。"
         "可靠覆盖使用每套 120 条的 BY 校正。",
         "## 1. 品类差异与跨期保持",
         show(["分群","组合长度","Disc 真实","Disc B2 中位","Disc 超出","Disc B2 ≥ L",
               "Val 真实","Val B2 中位","Val 超出","Val B2 ≥ L"],rows),
         "[S、A1、B2 明细](distinct_summary.csv) · [真实逐群](distinct_groups.csv) · [跨期画像配对](profile_cross_phase.csv)",
         "## 2. 篮子大小匹配随机对照"]
    ctr=read("validation_controls")
    labels={"raw_coverage":"全店覆盖","reliable_coverage":"可靠覆盖","hit_at_5":"Hit@5","quality_pass_share":"质量通过率"}
    txt.append(show(["分群","对照","指标","真实","随机中位","随机 ≥ 真实"],[
        (LABEL[r.variant],r.control,labels[r.metric],pct(r.real),pct(r.median),f"{r.random_ge}/100")
        for r in ctr.itertuples()]))
    txt += ["## 3. G 贪心与规则覆盖重叠"]
    system=read("validation_systems")
    result=system.loc[system.control.eq("GL")].set_index("method")
    paired=read("validation_paired").set_index("metric")
    rows=[]
    for method in LABEL:
        r=result.loc[method]
        row=[LABEL[method]]
        for m in ("raw_coverage","reliable_coverage","hit_at_5"):
            cell=pct(r[m])
            if method!="G":
                band=paired.loc[f"{method}_minus_G:{m}"]
                cell+=f" ({100*band.L_minus_G:+.2f} [{100*band.low95:+.2f}, {100*band.high95:+.2f}] pp)"
            row.append(cell)
        rows.append(row)
    txt.append(show(["方法","全店覆盖（较 G）","可靠覆盖（较 G）","Hit@5（较 G）"],rows))
    txt += ["[贪心每步新增覆盖](G_greedy_discovery.csv) · [相对 G 独有订单](validation_overlap.csv)",
            "## 4. 分群稳定性与缩放"]
    stability=read("stability_summary")
    robust=system.loc[system.control.eq("ROBUST")].set_index("method")
    rows=[]
    for r in stability.itertuples():
        data=(result if r.scaler=="zscore" else robust).loc[r.variant]
        rows.append((LABEL[r.variant],r.scaler,f"{r.silhouette:.3f}",f"{r.mean_ari:.3f} ± {r.sd_ari:.3f}",
                     "—" if pd.isna(r.ari_vs_zscore) else f"{r.ari_vs_zscore:.3f}",
                     pct(data.raw_coverage),pct(data.reliable_coverage),pct(data.hit_at_5)))
    txt.append(show(["分群","缩放","轮廓","重抽 ARI","相对 z-score ARI","全店覆盖","可靠覆盖","Hit@5"],rows))
    txt += ["[补测协议](../README.md) · [过程审计](audit.json) · [全系统](validation_systems.csv)"]
    (OUT/"README.md").write_text("\n\n".join(txt)+"\n",encoding="utf-8")


if __name__=="__main__":
    main()
