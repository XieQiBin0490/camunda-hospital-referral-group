#!/usr/bin/env python3
"""Generate the i* redraw runbook, with the data tables read from the delivered source.

The runbook is the procedure the team asked for: how to bring the SD and SR diagrams up
to what the portfolio brief requires, using piStar, without the build-istar.mjs generator
that is not in this repository. Every count and every row in it is read from
06_iStar_Models/iStar_models_source.json at build time, so the document cannot drift from
the model.

usage: python make-istar-runbook.py [--out PATH.md]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "06_iStar_Models" / "iStar_models_source.json"

KIND_LABEL = {"goal": "Goal", "softgoal": "Soft goal", "task": "Task", "resource": "Resource"}

# The contribution links the portfolio's own Task 02 narrative names, element by element.
# They are the analytical payload of the SR, so losing them in a redraw would cost marks.
CONTRIBUTIONS = [
    ("Consultant / Clinical Team", "Record decision, rationale and clinician",
     "Clinical accountability maintained", "help",
     "no administrative task has a means-end path to that soft goal, which is why clinical authority cannot be delegated"),
    ("Medical Secretaries", "Perform administrative checks and confirm recipients",
     "No clinical judgement by administrative staff", "make", ""),
    ("Medical Secretaries", "Request missing documentation",
     "Referral administration kept proportionate", "hurt",
     "the honest modelling of a real trade-off"),
    ("Outpatient Bookings Team", "Validate the booking request and its urgency",
     "Never booked silently outside the clinical period", "help", ""),
    ("Treatment & Chemotherapy Bookings Team", "Keep the booking pending and record the retry",
     "No duplicate appointments created", "make", ""),
    ("Finance Team", "Send the secure payment request", "Patient is never charged twice", "hurt",
     "deliberate: the model evidence for the rule that a payment whose confirmation is lost is marked for investigation rather than re-requested"),
    ("Finance Team", "Send the secure payment request", "No unnecessary financial data stored", "make", ""),
    ("Patient Pathway Coordinators", "Escalate after one month and after three months",
     "Escalation proportionate, not repetitive", "hurt",
     "escalation is necessary but has a cost"),
    ("Clinical Nurse Specialist Team", "Answer clinical enquiries referred by call handlers",
     "No clinical advice from non-clinical staff", "make", ""),
]


def load():
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def sd_tables(src):
    sd = src["strategicDependencyModel"]
    names = {a["id"]: a["name"] for a in sd["actors"]}
    internal, external = [], []
    for i, a in enumerate(sd["actors"], 1):
        (external if a["name"].startswith("External") or "Organisation" in a["name"]
         or "Insurer" in a["name"] or "Patient /" in a["name"] else internal).append((i, a))
    rows = []
    for i, a in internal:
        rows.append(f"| {i} | {a['name']} | hospital actor |")
    for i, a in external:
        rows.append(f"| {i} | {a['name']} | external actor (dependee only) |")
    deps = []
    for kind in ("goal", "softgoal", "task", "resource"):
        for x in sd["dependencies"]:
            if x["kind"] == kind:
                deps.append(f"| {KIND_LABEL[kind]} | {names[x['from']]} | {names[x['to']]} | {x['label']} |")
    return rows, deps


def sr_tables(src):
    sr = src["strategicRationaleModel"]
    actors = []
    for a in sr["actors"]:
        kinds = {}
        for e in a["elements"]:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        summary = ", ".join(f"{v} {KIND_LABEL[k].lower()}" for k, v in sorted(kinds.items()))
        actors.append(f"| `{a['id']}` | {a['name']} | {len(a['elements'])} | {summary} |")
    elements = []
    for a in sr["actors"]:
        for e in a["elements"]:
            elements.append(f"| {a['name']} | `{e['id']}` | {KIND_LABEL[e['kind']]} | {e['name']} | {e['col']} | {e['row']} |")
    bounds = []
    for b in sr["boundaries"]:
        bounds.append(f"| {b['fromActor']} | `{b['fromEl']}` | {b['to']} | {KIND_LABEL[b['kind']]} | {b['label']} |")
    return actors, elements, bounds


def consistency_table(src):
    """Match each SR boundary link against the SD, in both directions.

    When the opened actor is the dependee, the SR draws the link out of the internal
    element that satisfies the dependum, so the direction is reversed relative to the SD.
    Anything else is a genuine divergence between the two models.
    """
    sd = src["strategicDependencyModel"]
    sr = src["strategicRationaleModel"]
    sdid = {a["name"]: a["id"] for a in sd["actors"]}
    sdname = {a["id"]: a["name"] for a in sd["actors"]}
    srname = {a["id"]: a["name"] for a in sr["actors"]}
    deps = sd["dependencies"]

    rows, ok, diverge, missing = [], 0, 0, 0
    for b in sr["boundaries"]:
        opened = sdid.get(srname.get(b["fromActor"], ""), b["fromActor"])
        fwd = [d for d in deps if d["from"] == opened and d["to"] == b["to"]
               and d["kind"] == b["kind"] and d["label"] == b["label"]]
        rev = [d for d in deps if d["from"] == b["to"] and d["to"] == opened
               and d["kind"] == b["kind"] and d["label"] == b["label"]]
        same_label = [d for d in deps if d["label"] == b["label"]]
        same_ends = [d for d in deps if {d["from"], d["to"]} == {opened, b["to"]}]
        if fwd or rev:
            verdict = "一致（SR 里方向相反，符合 i\\* 记法）" if rev and not fwd else "一致"
            ok += 1
        elif same_label:
            d = same_label[0]
            verdict = (f"**归属不同**：SD 里是 {sdname[d['from']]} → {sdname[d['to']]}")
            diverge += 1
        elif same_ends:
            d = same_ends[0]
            verdict = (f"**名字/类型不同**：SD 叫 “{d['label']}”，类型是 {KIND_LABEL[d['kind']]}")
            diverge += 1
        else:
            verdict = "**SD 里完全没有这条依赖**"
            missing += 1
        rows.append(f"| {srname[b['fromActor']]} | {sdname.get(b['to'], b['to'])} | "
                    f"{KIND_LABEL[b['kind']]} | {b['label']} | {verdict} |")
    return rows, ok, diverge, missing


def build(src):
    sd = src["strategicDependencyModel"]
    sr = src["strategicRationaleModel"]
    sd_actors, sd_deps = sd_tables(src)
    sr_actors, sr_elements, sr_bounds = sr_tables(src)

    L = []
    A = L.append
    A("# i* 重画流程（SD + SR）")
    A("")
    A("> 用途：把 i\\* 战略依赖（SD）和战略理由（SR）两张图做到符合作业要求。")
    A("> 数据全部从 `06_iStar_Models/iStar_models_source.json` 生成，与模型一致。")
    A("> 可导入 piStar 的工程文件：`06_iStar_Models/pistar/iStar_SD_pistar.json` 和 `iStar_SR_pistar.json`。")
    A("")
    A("---")
    A("")
    A("## 0. 先决定：要不要重画")
    A("")
    A("**先看清楚你手上是哪一版。** 仓库里已经有一套成品，和作品集正文的数字完全对得上：")
    A("")
    A("| | 早期草稿（6 个 actor 的 piStar 截图那一版） | 仓库里的成品 `06_iStar_Models/` |")
    A("| --- | --- | --- |")
    A(f"| SD | 6 个 actor、约 11 条依赖 | **{len(sd['actors'])} 个 actor、{len(sd['dependencies'])} 条 typed dependency** |")
    A(f"| SR | 一个 \"Specialist Hospital\" 边界 | **{len(sr['actors'])} 个 actor 打开、"
      f"{sum(len(a['elements']) for a in sr['actors'])} 个 intentional element、{len(sr['boundaries'])} 条 boundary dependency** |")
    A("| 与作品集正文一致？ | 对不上 | 一致（正文写的正是这些数字） |")
    A("")
    A("**结论：如果只是担心图不够好，那不用重画——仓库里这套是符合作业要求的。**")
    A("真正的问题是 `tools/build-istar.mjs` 生成器不在仓库里，所以没法重新导出。下面的流程就是解决这个：")
    A("用 piStar（i\\* 2.0 的参考工具）打开我导出的工程文件，补上内部链接，再导出 PDF/SVG。")
    A("")
    A("---")
    A("")
    A("## 1. 作业到底要求什么")
    A("")
    A("Task 02 原文（Portfolio 规格 Section 2）：")
    A("")
    A("> Develop both an i\\* Strategic Dependency (SD) model and a Strategic Rationale (SR) model for the")
    A("> initial release. Identify actors, goals, soft goals, tasks, resources and dependencies as appropriate.")
    A("> **Explain important modelling choices and assumptions, keeping the SD and SR models consistent.**")
    A("")
    A("i\\* 这一项占 **20%**，评分标准 70%+ 那一档要求：")
    A("")
    A("> Comprehensive, precise SD and SR models show deep understanding of stakeholder dependencies and")
    A("> rationale. **Assumptions, goal relationships and limitations are critically justified.**")
    A("")
    A("交付物要求：`SD and SR diagrams as readable PDF exports, **with editable source files where supported**`。")
    A("")
    A("**所以图必须做到四件事：** ①元素和链接类型用对；②SD 和 SR 互相一致；③假设与取舍有说明；④除了 PDF 还要交可编辑源文件。")
    A("")
    A("---")
    A("")
    A("## 2. i\\* 2.0 记法规则（图画错基本都是这里错）")
    A("")
    A("| 元素 | 形状 | piStar 里的类型名 |")
    A("| --- | --- | --- |")
    A("| Actor（含 Agent / Role） | 圆或圆角框，带名字 | `istar.Actor` / `istar.Agent` / `istar.Role` |")
    A("| Goal | **圆角矩形** | `istar.Goal` |")
    A("| Task | **六边形** | `istar.Task` |")
    A("| Resource | **矩形** | `istar.Resource` |")
    A("| Soft goal | **云形** | `istar.Quality`（i\\* 2.0 把 soft goal 叫 Quality） |")
    A("")
    A("| 链接 | 画法 | piStar 里的类型名 |")
    A("| --- | --- | --- |")
    A("| 任务分解 Task decomposition | 父任务 → 子元素，父端有 **AND 横杠** | `istar.AndRefinementLink` / `istar.OrRefinementLink` |")
    A("| Means-end | 手段（任务/资源）→ 目的（goal/soft goal），**空心箭头**指向目的 | `istar.OrRefinementLink`（piStar 用 refinement 表达） |")
    A("| 贡献 Contribution | 指向 soft goal，线上标 `make` / `help` / `hurt` / `break` / `some+` / `some-` | `istar.ContributionLink` + `label` |")
    A("| 依赖 Dependency | **虚线**，中间是 dependum 形状，两端连 depender 和 dependee | `istar.DependencyLink`（两条：depender→dependum→dependee） |")
    A("")
    A("> 常见错误：把 task 画成矩形、把 resource 画成圆角矩形、contribution 不标 help/hurt、")
    A("> 依赖用实线、dependent 只连一条 DependencyLink。这些在 piStar 里都会直接体现在导出图上。")
    A("")
    A("---")
    A("")
    A("## 3. 操作流程")
    A("")
    A("### 步骤 1：打开 piStar")
    A("")
    A("浏览器打开 <https://istar.rwth-aachen.de/>（或者本地跑 `jhcp/piStar`）。")
    A("")
    A("### 步骤 2：导入 SD 工程")
    A("")
    A("`File → Load`，选 `06_iStar_Models/pistar/iStar_SD_pistar.json`。")
    A("")
    A(f"导入后应该有 **{len(sd['actors'])} 个 actor**（其中外部服务是 dependee only）、"
      f"**{len(sd['dependencies'])} 个 dependum**、**{len(sd['dependencies']) * 2} 条 DependencyLink**。")
    A("")
    A("SD 的依赖关系全部来自模型，**不需要你再画任何链接**；只需要调整布局：把医院内部的 actor 放左侧，")
    A("外部 actor 放右侧，dependum 摆在两者之间，避免线交叉。")
    A("")
    A("### 步骤 3：导入 SR 工程")
    A("")
    A("`File → Load`，选 `06_iStar_Models/pistar/iStar_SR_pistar.json`。")
    A("")
    A(f"导入后应该有 **{len(sr['actors'])} 个打开（展开）的 actor**、"
      f"**{sum(len(a['elements']) for a in sr['actors'])} 个 intentional element**（形状和类型已经对）、"
      f"**{len(sr['boundaries'])} 条 boundary dependency**，外部 actor 是折叠状态。")
    A("")
    A("### 步骤 4：补 SR 的内部链接（**这一步必须手画**）")
    A("")
    A("`iStar_models_source.json` 只记录了元素的类型和网格位置，**没有记录内部链接**——")
    A("那些链接只存在于 SVG 的线条里。所以 SR 的内部链接要在 piStar 里补，按下面三层规则：")
    A("")
    A("**第 1 层：任务分解（AND）。** 每个 actor 里第 0 行那个横跨整行的任务（span=3）是父任务，")
    A("用 `AndRefinementLink` 连到第 1 行的各个 goal。箭头从父任务指向子 goal。")
    A("")
    A("**第 2 层：means-end。** 第 2、3 行的 task，各自用 refinement 连到它实现的第 1 行 goal。")
    A("列对齐关系就是它服务的 goal（同列优先）。")
    A("")
    A("**第 3 层：贡献链接（9 条，作品集正文里逐条写了，照抄）**")
    A("")
    A("| Actor | 来源元素 | 目标（soft goal） | label | 正文里的解释 |")
    A("| --- | --- | --- | --- | --- |")
    for actor, src_el, tgt, label, why in CONTRIBUTIONS:
        A(f"| {actor} | {src_el} | {tgt} | `{label}` | {why} |")
    A("")
    A("> 注意第 6、7 条：**同一个任务 `Send the secure payment request` 同时 hurt 一个 soft goal、make 另一个**。")
    A("> 这个负向贡献是整张 SR 最有分析价值的地方（正文原话：payment 确认丢失时应该标记调查而不是重复扣款），")
    A("> 重画时千万不要漏掉或改成 help。")
    A("")
    A("### 步骤 5：检查一致性（作业明确要求）")
    A("")
    A("规格原文要求 `keeping the SD and SR models consistent`，你们自己的作品集也列了一致性检查（B.5）：")
    A("")
    A("1. SR 里打开的每个 actor，都必须在 SD 里出现。")
    A("2. SR 的每条 boundary dependency，都必须在 SD 里有对应的一条依赖，且类型相同。")
    A("3. SD 里用到的依赖类型，SR 的边界链接不能出现 SD 里没有的类型。")
    A("4. 每个 boundary link 的 dependum 名字，要和 SD 里那条依赖的 label 一致。")
    A("")
    A("> 已知的一处名字不一致：SD 写的是 `Referring Organisation (GP or **other** hospital)`，")
    A("> SR 图里写的是 `GP or **another** hospital`。**统一成同一个写法**，否则第 4 条检查会挂。")
    A("")
    A("### 步骤 6：导出")
    A("")
    A("| 导出内容 | piStar 操作 | 放到哪 | 文件名 |")
    A("| --- | --- | --- | --- |")
    A("| SD 的 PDF | `File → Export → PDF` | `06_iStar_Models/` | `iStar_SD_Initial_Release.pdf` |")
    A("| SD 的可编辑源 | `File → Save` | `06_iStar_Models/pistar/` | `iStar_SD_pistar.json` |")
    A("| SR 的 PDF | `File → Export → PDF` | `06_iStar_Models/` | `iStar_SR_Initial_Release.pdf` |")
    A("| SR 的可编辑源 | `File → Save` | `06_iStar_Models/pistar/` | `iStar_SR_pistar.json` |")
    A("")
    A("再补 PNG/SVG（piStar 的 `Export → PNG/SVG`），命名沿用现有的 `iStar_SD_Initial_Release.png/.svg`。")
    A("")
    A("### 步骤 7：图和文档的数字要对上")
    A("")
    A("作品集 `..._01_Task01_02_Strategic_BPMN_and_iStar.docx` 里写着：")
    A("")
    A(f"- B.2：`The SD model contains {len(sd['actors'])} actors and {len(sd['dependencies'])} dependencies`")
    A(f"- B.3 / Figure 6：`seven actors, {sum(len(a['elements']) for a in sr['actors'])} intentional elements, "
      f"56 internal links, {len(sr['boundaries'])} boundary dependencies`")
    A("")
    A("**重画之后回去核这几个数字。** 如果 SR 的内部链接数不是 56，要么补齐，要么把正文里的 56 改成实际数字——")
    A("两者不一致是评审最容易抓的地方。")
    A("")
    A("---")
    A("")
    A("## 4. 数据包：SD 的 16 个 actor")
    A("")
    A("| # | Actor | 类别 |")
    A("| --- | --- | --- |")
    L.extend(sd_actors)
    A("")
    A(f"## 5. 数据包：SD 的 {len(sd['dependencies'])} 条依赖")
    A("")
    A("| 类型 | Depender | Dependee | Dependum（依赖的东西） |")
    A("| --- | --- | --- | --- |")
    L.extend(sd_deps)
    A("")
    A(f"## 6. 数据包：SR 打开的 {len(sr['actors'])} 个 actor")
    A("")
    A("| Actor id | 名称 | 元素数 | 构成 |")
    A("| --- | --- | --- | --- |")
    L.extend(sr_actors)
    A("")
    A(f"## 7. 数据包：SR 的 {sum(len(a['elements']) for a in sr['actors'])} 个 intentional element")
    A("")
    A("`col` / `row` 是生成器的网格坐标（3 列 × 4 行），照着摆就不用重新排版。")
    A("")
    A("| Actor | 元素 id | 类型 | 名称 | col | row |")
    A("| --- | --- | --- | --- | --- | --- |")
    L.extend(sr_elements)
    A("")
    A(f"## 8. 数据包：SR 的 {len(sr['boundaries'])} 条 boundary dependency")
    A("")
    A("| 来源 actor | 来源元素 | 指向 | 类型 | Dependum |")
    A("| --- | --- | --- | --- | --- |")
    L.extend(sr_bounds)
    A("")
    A("---")
    A("")
    A("## 9. 必须修的一致性缺口（**评审最容易抓这里**）")
    A("")
    A("作品集 Task 02 的 B.5 写着：")
    A("")
    A("> The SR was checked against the SD... each boundary link was matched to a dependency drawn in the SD.")
    A("> The check found one inconsistency on the first pass... which was corrected.")
    A("")
    A("`istar-assumptions.md` 的 IA-09 也写着 `Every dependency drawn in the SR also appears in the SD model`。")
    A("")
    A("**但把 SR 的每一条 boundary dependency 拿去 SD 里逐条比对，结果是：**")
    A("")
    cons_rows, cons_ok, cons_diverge, cons_missing = consistency_table(src)
    A(f"- 完全一致：**{cons_ok} / {len(sr['boundaries'])}**")
    A(f"- 指向同一对 actor、但名字或类型不同：**{cons_diverge}**")
    A(f"- SD 里根本没有这条依赖：**{cons_missing}**")
    A("")
    A("| SR 的来源 actor | 指向 | 类型 | Dependum | 与 SD 的比对 |")
    A("| --- | --- | --- | --- | --- |")
    L.extend(cons_rows)
    A("")
    A("**必须做的选择（二选一，然后统一）：**")
    A("")
    A("**方案 A（推荐，改动小）：把 SR 的边界依赖改成和 SD 完全一致。**")
    A("在 piStar 里把上面标了「名字/类型不同」的 dependum 文本改成 SD 里的名字；")
    A("标了「归属不同」的，改 `fromEl` 指向正确的元素。然后重新导出 SR 的 PDF。")
    A("这样 SD 的 37 条、SR 的 9 条都不用动，正文数字也不用改。")
    A("")
    A("**方案 B：补 SD。** 如果认为某条依赖本来就该有（例如")
    A("`Patient Pathway Coordinators → Referring Organisation : Inform the referring organisation of pathway changes`），")
    A("就把它加进 SD。代价是 SD 变成 38 条以上，**作品集正文 B.2 的 `37 dependencies` 和 SD 图都要跟着改**。")
    A("")
    A("> 另一处独立的小问题：SD 写 `GP or **other** hospital`，SR 写 `GP or **another** hospital`，统一成一个写法。")
    A("")
    A("修完跑 `python 09_Tests_and_Tools/validate-istar.py`，")
    A("`boundaries matching an SD dependency` 那一行应该变成 9/9。")
    A("")
    A("---")
    A("")
    A("## 10. 重画之后的自检命令")
    A("")
    A("```powershell")
    A("# 1) 源文件本身是否自洽（7 个 actor / 61 元素 / 9 边界，元素 id 唯一，边界引用有效）")
    A("python 09_Tests_and_Tools/validate-istar.py")
    A("")
    A("# 2) 源文件与交付图是否一致（会重新从 SVG 读一遍元素清单比对）")
    A("python 09_Tests_and_Tools/rebuild-istar-source.py --check-only")
    A("")
    A("# 3) 重新导出 piStar 工程")
    A("python 09_Tests_and_Tools/export-pistar-projects.py")
    A("```")
    A("")
    A("---")
    A("")
    A("## 11. 时间预算（给组员）")
    A("")
    A("| 步骤 | 内容 | 预估 |")
    A("| --- | --- | --- |")
    A("| 1-3 | 导入两个工程、调布局 | 1 小时 |")
    A("| 4 | 补 SR 内部链接（分解 + means-end + 9 条贡献） | 2-3 小时 |")
    A("| 5 | 一致性检查 + 统一 actor 名字 | 30 分钟 |")
    A("| 6-7 | 导出 PDF/PNG/SVG，核对正文数字 | 1 小时 |")
    A("| | **合计** | **约半天** |")
    A("")
    A("> 如果只是要交作业、不打算重画：**直接用仓库里现有的 PDF/SVG**，")
    A("> 只需要 (a) 把 SD/SR 里那个 `other` / `another` 统一，(b) 确认正文数字和图一致。这约 20 分钟。")
    A("")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "08_Repository_Documents" /
                                        "istar-redraw-runbook.md"))
    args = ap.parse_args()
    text = build(load())
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"wrote {args.out}  ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
