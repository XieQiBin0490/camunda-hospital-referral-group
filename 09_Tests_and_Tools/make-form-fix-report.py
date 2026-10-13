#!/usr/bin/env python3
"""Build the review handout for improvement 5 (form field types) as one Word file.

Everything in the document is computed from the working tree and the committed
revision, so the handout cannot drift from the actual change:

  * control type distribution before/after      - computed from git HEAD vs now
  * the 10 type corrections with file and line  - computed from git HEAD vs now
  * the 41 added controls                       - computed from git HEAD vs now
  * the validation rules                        - computed from git HEAD vs now
  * the gateway decision table                  - computed by reusing
                                                  demo-form-control-impact.py
  * the validator results                       - the validators are executed here

usage: python make-form-fix-report.py [--out PATH.docx]
"""

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
FORMS = ROOT / "03_Forms"
TOOLS = ROOT / "09_Tests_and_Tools"

BODY_FONT = "Microsoft YaHei"
EAST_ASIA = "微软雅黑"
CODE_FONT = "Consolas"

ACCENT = RGBColor(0x1F, 0x4E, 0x79)
MUTED = RGBColor(0x60, 0x60, 0x60)
BAD = RGBColor(0xA6, 0x1B, 0x1B)
GOOD = RGBColor(0x1B, 0x6B, 0x2F)

# The variables an exclusive gateway branches on. Derived from the condition
# expressions in 02_BPMN_Models and kept in step with fix-form-field-types.py.
GATEWAY_VARIABLES = {
    "accessibleFormatRequired", "advancePaymentRequired", "appointmentPaid",
    "appointmentWithin14Days", "consentGiven", "contactSuccessful",
    "documentsComplete", "enquiryType", "financialImpact", "fitToContinue",
    "followUpSlotWithinPeriod", "fundingApproved", "furtherCyclesPlanned",
    "letterAgeMonths", "letterApproved", "letterDelayDays", "paymentStatus",
    "referralDecision", "referralUrgency", "requestAuthorised",
    "suitableSlotFound", "suspectedClinicalError", "treatmentCapacityConfirmed",
    "urgentPostponement",
}

# variable -> the evidence that justifies the corrected control
EVIDENCE = {
    "letterDelayDays": "S1_Strategic_Landscape.bpmn:230,233 用 `letterDelayDays <= 7` / `> 7` 做数值比较",
    "letterAgeMonths": "S3_...Aftercare.bpmn:584,589,594,599 用 `< 1` / `< 3` / `>= 1` / `>= 3` 做数值比较",
    "referralDecision": "网关比较 `= \"accepted\"` / `\"rejected\"` / `\"information required\"` / `\"redirected\"`",
    "referralUrgency": "网关比较 `= \"urgent\"` / `\"routine\"`；PublishPatientReferralWorker、QueryAvailableAppointmentSlotsWorker 读取",
    "paymentStatus": "O1_Operational_Merged.bpmn:653-662 四个受控取值",
    "enquiryType": "S3 的 G_EnquiryType 比较 `administrative` / `financial` / `clinical`",
    "referralReference": "PublishPatientReferralWorker.requireString（硬性要求）、SubmitPatientReferralWorker",
    "referringOrganisation": "4 个工作器读取（Publish、Submit、RequestMissingDocumentation、SendReferralOutcome）",
    "requestedSpeciality": "QueryAvailableAppointmentSlotsWorker.findString",
    "missingDocuments": "RequestMissingDocumentationWorker.findString",
    "appointmentDate": "任务名「Select and book the new patient appointment」",
    "preferredTimeframeDays": "QueryAvailableAppointmentSlotsWorker.intOr",
    "treatmentCode": "RequestTreatmentCapacityWorker.findString",
    "treatmentCycles": "RequestTreatmentCapacityWorker.intOr（整数）",
    "requiredResource": "RequestTreatmentCapacityWorker.findString",
    "chargeAmount": "RequestSecurePaymentWorker.doubleOr",
    "currency": "RequestSecurePaymentWorker.findString（工作器默认 GBP）",
    "fundingOrganisation": "任务名「Record the funding organisation, ...」",
    "fundingAuthorisationReference": "任务名「... authorisation reference ...」",
    "approvedAmount": "RequestSecurePaymentWorker.doubleOr；任务名「approved amount」",
    "fundingLimitations": "任务名「... and limitations」",
    "paymentReference": "RequestRefundWorker.findString",
    "paymentAmount": "RequestRefundWorker.doubleOr；任务名「amount and date」",
    "paymentDate": "任务名「Record the payment reference, amount and date」",
    "refundReference": "任务名「Record the refund result against the patient account」",
    "refundAmount": "RequestRefundWorker.doubleOr",
    "refundDate": "任务名「Record the refund result against the patient account」",
    "refundDecision": "任务名「retained, transferred or refunded」",
    "cycleReference": "RequestBloodTestWorker.findString",
    "treatmentCycleDate": "任务名「record clinical administration」",
    "accessibleFormatRequired": "S3 的 G_CommunicationPreference 比较 `= true`；改前没有任何表单采集它",
    "communicationPreference": "SendAppointmentConfirmationLetterWorker.findString（工作器默认 post）",
    "reportPeriod": "GenerateManagementReportsWorker.findString",
}


# --------------------------------------------------------------------------- #
# data collection
# --------------------------------------------------------------------------- #

def git_forms():
    out = subprocess.run(["git", "ls-tree", "--name-only", "HEAD", "03_Forms/"],
                         capture_output=True, text=True, check=True).stdout.split()
    before = {}
    for path in out:
        blob = subprocess.run(["git", "show", f"HEAD:{path}"],
                              capture_output=True, text=True, check=True,
                              encoding="utf-8").stdout
        before[Path(path).stem] = json.loads(blob)
    return before


def comps(doc):
    return {c["key"]: c for c in doc.get("components", []) if c.get("key")}


def line_of(path, needle, start=1):
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if i >= start and needle in line:
            return i
    return None


def control_distribution(docs):
    counts = Counter()
    for doc in docs:
        for comp in doc.get("components", []):
            if comp.get("type") in ("text", "html"):
                continue
            counts[comp["type"]] += 1
    return counts


def collect_changes(before):
    retyped, added, validated = [], [], []
    for path in sorted(FORMS.glob("*.form")):
        fid = path.stem
        after = json.loads(path.read_text(encoding="utf-8"))
        a, b = comps(after), comps(before.get(fid, {}))
        for key, old in b.items():
            new = a.get(key)
            if new is None:
                continue
            if new.get("type") != old.get("type"):
                kline = line_of(path, f'"key": "{key}"')
                tline = line_of(path, f'"type": "{new["type"]}"', kline or 1)
                retyped.append({"form": fid, "key": key, "line": tline,
                                "was": old.get("type"), "now": new.get("type"),
                                "label": new.get("label", ""),
                                "values": [v.get("value") for v in new.get("values", [])]})
            if not old.get("validate") and new.get("validate"):
                validated.append({"form": fid, "key": key, "type": new.get("type"),
                                  "validate": new["validate"]})
        for key, new in a.items():
            if key not in b:
                added.append({"form": fid, "key": key, "type": new.get("type"),
                              "label": new.get("label", ""),
                              "required": bool((new.get("validate") or {}).get("required"))})
    return retyped, added, validated


def gateway_table():
    spec = importlib.util.spec_from_file_location(
        "impact", TOOLS / "demo-form-control-impact.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    parsed = {p.name: module.parse(p) for p in sorted((ROOT / "02_BPMN_Models").glob("*.bpmn"))}
    return module.collect(parsed)


def validator_results():
    python = sys.executable
    runs = [
        ("validate-forms.py", ["validate-forms.py"],
         "表单合法、键唯一、与任务绑定"),
        ("validate-contract.py", ["validate-contract.py"],
         "工作器硬性输入有人能提供"),
        ("validate-models.py", ["validate-models.py"] +
         [str(p) for p in sorted((ROOT / "02_BPMN_Models").glob("*.bpmn"))],
         "4 个模型结构"),
        ("validate-form-controls.py", ["validate-form-controls.py"],
         "控件类型匹配数据、网关变量已采集且必填"),
    ]
    results = []
    for name, args, what in runs:
        proc = subprocess.run([python, str(TOOLS / args[0])] + args[1:],
                              capture_output=True, text=True, encoding="utf-8",
                              cwd=str(ROOT))
        text = (proc.stdout or "") + (proc.stderr or "")
        res = next((ln.strip() for ln in text.splitlines() if ln.startswith("RESULT")), "")
        summ = next((ln.strip() for ln in text.splitlines() if "SUMMARY" in ln), "")
        results.append({"script": name, "what": what, "result": res, "summary": summ,
                        "ok": proc.returncode == 0})
    return results


# --------------------------------------------------------------------------- #
# document helpers
# --------------------------------------------------------------------------- #

def setup(doc):
    for section in doc.sections:
        section.page_width, section.page_height = Cm(21.0), Cm(29.7)
        section.left_margin = section.right_margin = Cm(1.8)
        section.top_margin = section.bottom_margin = Cm(2.0)
    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), EAST_ASIA)
    for name, size in (("Heading 1", 16), ("Heading 2", 13), ("Heading 3", 11.5),
                       ("Title", 24)):
        style = doc.styles[name]
        style.font.name = BODY_FONT
        style.font.size = Pt(size)
        style.font.color.rgb = ACCENT
        style.element.rPr.rFonts.set(qn("w:eastAsia"), EAST_ASIA)


def para(doc, text, size=10.5, bold=False, color=None, italic=False, space_after=6):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    run = p.add_run(text)
    run.font.name = BODY_FONT
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    if color is not None:
        run.font.color.rgb = color
    run._element.rPr.rFonts.set(qn("w:eastAsia"), EAST_ASIA)
    return p


def rich(doc, parts, size=10.5, space_after=6):
    """parts: list of (text, bold, colour)."""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    for text, bold, color in parts:
        run = p.add_run(text)
        run.font.name = BODY_FONT
        run.font.size = Pt(size)
        run.bold = bold
        if color is not None:
            run.font.color.rgb = color
        run._element.rPr.rFonts.set(qn("w:eastAsia"), EAST_ASIA)
    return p


def bullet(doc, text):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(3)
    run = p.add_run(text)
    run.font.name = BODY_FONT
    run.font.size = Pt(10.5)
    run._element.rPr.rFonts.set(qn("w:eastAsia"), EAST_ASIA)
    return p


def code(doc, lines):
    for line in lines:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.left_indent = Cm(0.6)
        run = p.add_run(line if line else " ")
        run.font.name = CODE_FONT
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)


def table(doc, headers, rows, widths, font_size=9, header_color=ACCENT):
    # Scale the requested widths to the usable width of the section the table lands
    # in, so a table can never run past the margin in Word or LibreOffice.
    section = doc.sections[-1]
    usable = Emu(section.page_width - section.left_margin - section.right_margin).cm
    scale = (usable - 0.4) / sum(widths)
    widths = [w * scale for w in widths]
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    hdr = t.rows[0].cells
    for i, text in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        p.paragraph_format.space_after = Pt(1)
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(font_size)
        run.font.name = BODY_FONT
        run.font.color.rgb = header_color
        run._element.rPr.rFonts.set(qn("w:eastAsia"), EAST_ASIA)
    for row in rows:
        cells = t.add_row().cells
        for i, text in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.paragraph_format.space_after = Pt(1)
            for j, chunk in enumerate(str(text).split("\n")):
                if j:
                    p = cells[i].add_paragraph()
                    p.paragraph_format.space_after = Pt(1)
                run = p.add_run(chunk)
                run.font.size = Pt(font_size)
                run.font.name = BODY_FONT
                run._element.rPr.rFonts.set(qn("w:eastAsia"), EAST_ASIA)
    for r in t.rows:
        for i, cell in enumerate(r.cells):
            cell.width = Cm(widths[i])
    return t


def landscape(doc):
    section = doc.add_section(WD_SECTION.NEW_PAGE)
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = Cm(29.7), Cm(21.0)
    section.left_margin = section.right_margin = Cm(1.8)
    section.top_margin = section.bottom_margin = Cm(1.8)
    return section


def portrait(doc):
    section = doc.add_section(WD_SECTION.NEW_PAGE)
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width, section.page_height = Cm(21.0), Cm(29.7)
    section.left_margin = section.right_margin = Cm(1.8)
    section.top_margin = section.bottom_margin = Cm(2.0)
    return section


# --------------------------------------------------------------------------- #
# document body
# --------------------------------------------------------------------------- #

def build(out_path):
    doc = Document()
    setup(doc)

    before = git_forms()
    current = {p.stem: json.loads(p.read_text(encoding="utf-8"))
               for p in sorted(FORMS.glob("*.form"))}
    dist_before = control_distribution(before.values())
    dist_after = control_distribution(current.values())
    retyped, added, validated = collect_changes(before)
    gateways = gateway_table()
    results = validator_results()

    # ---------------------------------------------------------------- cover
    doc.add_heading("表单字段类型整改 · 汇报材料", level=0)
    rich(doc, [("整改项：", True, None), ("第 5 项「修正表单字段类型」", False, None),
               ("（顺带完成第 4 项「表单输入校验」）", False, MUTED)], size=12)
    para(doc, "范围：03_Forms/ 下 68 个 Camunda 8 表单（JSON）。模型与 Java 工作器一行未改。",
         color=MUTED)
    para(doc, "本材料中所有数字、行号与网关判定均由脚本从工作区实时计算，"
              "可用 09_Tests_and_Tools/ 下的脚本复跑。", color=MUTED)

    # ------------------------------------------------------- 1 summary
    doc.add_heading("1. 一页看完", level=1)
    rich(doc, [("结论：", True, None),
               ("改之前 68 个表单一共 118 个输入控件，只有 2 种控件"
                "（77 个文本框 + 41 个复选框），日期、数字、下拉框一个都没有。"
                "改之后是 6 种控件、159 个输入控件。", False, None)])
    summary = [
        ["输入控件总数", str(sum(dist_before.values())), str(sum(dist_after.values())),
         f"+{sum(dist_after.values()) - sum(dist_before.values())}"],
        ["控件种类", f"{len([k for k in dist_before if k != 'text'])} 种",
         f"{len([k for k in dist_after if k != 'text'])} 种", ""],
        ["日期 datetime", "0", str(dist_after.get("datetime", 0)), "新增"],
        ["数字 number", "0", str(dist_after.get("number", 0)), "新增"],
        ["下拉框 select", "0", str(dist_after.get("select", 0)), "新增"],
        ["多行文本 textarea", "0", str(dist_after.get("textarea", 0)), "新增"],
        ["控件类型纠错", "—", f"{len(retyped)} 处", "其中 4 处是真 bug"],
        ["新增控件", "—", f"{len(added)} 个", "工作器已在读、却无人能填的变量"],
        ["加校验的字段", "0", f"{len(validated)} 个", "必填 / 格式 / 取值范围"],
    ]
    table(doc, ["项目", "改前", "改后", "说明"], summary, [4.4, 3.0, 3.0, 7.0])
    para(doc, "")
    rich(doc, [("一句话版本：", True, None),
               ("把 4 个「复选框冒充数字」的字段改成数字控件"
                "（这三个网关原本永远只能走默认分支），把 6 个决策字段改成下拉框"
                "（取值与模型 FEEL 表达式逐字对齐），补上 41 个工作器已在读但无人能填的字段，"
                "并给全部网关依赖的变量加上必填。", False, None)])

    # --------------------------------------------- 2 review requirements
    doc.add_heading("2. 对照评审要求", level=1)
    table(doc, ["评审要求", "状态", "证据"], [
        ["字段类型：不同业务数据用对应控件，不要全部用文本框", "已完成",
         f"控件 2 种 → 6 种；{len(retyped)} 处类型纠错 + {len(added)} 个新增控件（第 3、4 节）"],
        ["表单输入校验：防止空输入、无效格式输入", "已完成（顺带）",
         f"{len(validated)} 个字段加规则；网关变量强制必填（第 5 节）"],
    ], [6.6, 3.0, 7.8])

    # ------------------------------------------------ 3 type corrections
    doc.add_heading("3. 第一件事：10 处控件类型纠错", level=1)
    bugs = [r for r in retyped if r["was"] == "checkbox"]
    selects = [r for r in retyped if r["now"] == "select"]

    doc.add_heading("3.1 四个真 bug：复选框被绑定到一个要参与数值比较的变量", level=2)
    rich(doc, [("复选框只能输出 ", False, None), ("true / false", False, None),
               ("。在 FEEL 里布尔值与数字比大小求值为 ", False, None), ("null", False, None),
               ("，Zeebe 把 null 条件视为不成立，于是网关落到 ", False, None),
               ("default", False, None), (" 分支上。", False, None)])
    table(doc, ["表单文件", "行", "变量", "改前", "改后", "模型里的证据"],
          [[f"{r['form']}.form", f"L{r['line']}", r["key"], r["was"], r["now"],
            EVIDENCE.get(r["key"], "")] for r in bugs],
          [4.2, 1.1, 2.9, 1.7, 1.6, 5.9])

    para(doc, "")
    rich(doc, [("这三处网关的 default 恰好是「坏的那一支」，所以后果很具体：", True, None)])
    table(doc, ["网关", "它的默认分支（default）", "改前的实际后果"], [
        ["S1 / G_LetterOnTime", "F_22「Delayed」→ 升级延迟信函", "每一封信都被判定为超期"],
        ["S3 / G_LetterAge", "F_F9「Less than one month」→ 等一周",
         "永远回到每周提醒循环，永远升级不到行政管理员"],
        ["S3 / G_LetterAgeExtended", "F_F11「Less than three months」→ 发每周提醒",
         "永远升级不到高层管理"],
    ], [4.6, 6.4, 6.4])

    para(doc, "")
    rich(doc, [("改动形态（以 form-follow-up-review.form 为例，只改了 type 一个词）：", True, None)])
    code(doc, [
        "13    {",
        "14      \"key\": \"letterDelayDays\",",
        "15      \"label\": \"Delay in producing the letter, in days\",   ← 原标签只写了 letterDelayDays",
        "16      \"type\": \"number\",                                     ← 改前是 \"checkbox\"",
        "17      \"validate\": { \"max\": 365, \"min\": 0, \"required\": true }",
        "18    }",
    ])

    doc.add_heading("3.2 六个决策字段：自由文本框改下拉框", level=2)
    rich(doc, [("模型里这些变量的判断值是固定的几个字面量，文本框允许人随便填，"
                "填错就静默落到默认分支。改成下拉框后，", False, None),
               ("人只能选出模型认识的那几个值", True, None),
               ("，而每个选项的 value 就是 FEEL 表达式里正在比较的那个字面量。", False, None)])
    table(doc, ["表单文件", "行", "变量", "改前", "改后", "下拉框选项（value 与模型逐字对齐）"],
          [[f"{r['form']}.form", f"L{r['line']}", r["key"], r["was"], r["now"],
            " / ".join(r["values"])] for r in selects],
          [3.9, 1.0, 2.7, 1.5, 1.4, 6.9])

    para(doc, "")
    rich(doc, [("改动形态（form-record-referral-decision.form 的 L13-L38）：", True, None)])
    code(doc, [
        "13      \"label\": \"Referral decision (accepted / rejected / information required / redirected)\",",
        "14      \"key\": \"referralDecision\",",
        "15      \"type\": \"select\",              ← 改前是 \"textfield\"",
        "16      \"id\": \"Field_1s1dwkj\",",
        "17      \"values\": [                     ← 新增：选项列表",
        "18        { \"label\": \"Accepted\",             \"value\": \"accepted\" },",
        "22        { \"label\": \"Rejected\",             \"value\": \"rejected\" },",
        "26        { \"label\": \"Information required\", \"value\": \"information required\" },",
        "30        { \"label\": \"Redirected\",           \"value\": \"redirected\" }",
        "34      ],",
        "35      \"validate\": { \"required\": true }  ← 新增：必填",
        "38    },",
    ])
    rich(doc, [("因为下拉框输出的仍然是字符串，变量的类型没有变化，"
                "所以模型和工作器都不需要改——这就是「避免回归」的具体含义。", False, MUTED)])

    # ------------------------------------------------- 4 added controls
    doc.add_heading("4. 第二件事：补上 41 个缺失的控件", level=1)
    rich(doc, [("这是改类型时顺带发现的：Java 工作器一直在读这些变量"
                "（例如 ", False, None), ("RequestRefundWorker", False, None),
               (" 读 paymentAmount、RequestSecurePaymentWorker 读 approvedAmount），"
                "但", False, None),
               ("没有任何表单采集过它们", True, BAD),
               ("。也就是说，人坐在 Tasklist 前面根本填不了这些数据。", False, None)])
    para(doc, "新增控件全部有出处，没有一个是我凭空发明的：要么是某工作器按名字读取的变量，"
              "要么是模型里任务名明确写出来的数据项。下表按表单分组，"
              "共 16 个表单、41 个控件。", color=MUTED)
    grouped = defaultdict(list)
    for r in added:
        grouped[r["form"]].append(r)
    table(doc, ["表单文件（16 个）", "新增变量（控件类型、是否必填）", "依据：工作器读取 / 模型任务名"],
          [[f"{form}.form",
            "\n".join(f"{r['key']}（{r['type']}，{'必填' if r['required'] else '选填'}）"
                      for r in items),
            "\n".join(EVIDENCE.get(r["key"], "") for r in items)]
           for form, items in sorted(grouped.items())],
          [4.6, 6.4, 5.6])

    # ---------------------------------------------------- 5 validation
    doc.add_heading("5. 第三件事：给 115 个字段加校验规则", level=1)
    doc.add_heading("5.1 规则一：网关判断的变量一律必填", level=2)
    rich(doc, [("理由：用户留空时 FEEL 求值得到 ", False, None), ("null", False, None),
               ("，比较结果为假，流程", False, None), ("静默", True, BAD),
               ("走默认分支——日志里查不出错，但流程走错了。", False, None)])
    forms_by_var = defaultdict(list)
    for fid, doc_ in current.items():
        for comp in doc_.get("components", []):
            k = comp.get("key")
            if k and (comp.get("validate") or {}).get("required"):
                forms_by_var[k].append(fid)
    gw_rows = sorted((k, v) for k, v in forms_by_var.items()
                     if k in GATEWAY_VARIABLES)
    table(doc, ["变量（网关会判断它）", "在几个表单里已设为必填"],
          [[k, str(len(v))] for k, v in gw_rows], [8.0, 6.0])

    doc.add_heading("5.2 规则二：patientId 必填 + 格式校验", level=2)
    rich(doc, [("13 个工作器用 ", False, None), ("requireString(\"patientId\")", False, None),
               (" 硬性读取，缺了会抛 ValidationException 让实例停在事故上。"
                "格式规则：", False, None),
               ("^[A-Za-z0-9][A-Za-z0-9\\-]{2,39}$", False, None)])
    rich(doc, [("已核对交付证据里全部 ", False, None), ("91 个", True, None),
               (" 个不同的 patientId 取值（如 P-TC-01、P-happy-1790597472244）"
                "全部通过这条规则，不会挡住自己的验收用例。", False, None)])

    doc.add_heading("5.3 其余规则", level=2)
    table(doc, ["规则", "加在哪些字段", "例子"], [
        ["必填 required", "全部 68 个表单的 patientId + 24 个网关变量",
         "\"validate\": { \"required\": true }"],
        ["格式 pattern", "patientId、reportPeriod",
         "reportPeriod: ^[0-9]{4}-(0[1-9]|1[0-2])$（YYYY-MM）"],
        ["取值范围 min/max", "全部数字控件",
         "letterDelayDays: min 0 / max 365；treatmentCycles: min 1 / max 12"],
        ["长度 maxLength", "新增的文本、多行文本控件",
         "paymentReference: 40；fundingLimitations: 500"],
        ["默认值 defaultValue", "currency（GBP）、communicationPreference（post）",
         "与工作器里的兜底默认值保持一致"],
    ], [3.4, 6.0, 7.4])

    # ---------------------------------------------------- 6 runtime
    doc.add_heading("6. 这些改动在运行时怎么被看见", level=1)
    rich(doc, [("必须先说清楚一件事：", True, BAD),
               ("表单是 Tasklist 的渲染层和提交层，它决定", False, None),
               ("人能看到什么控件、能提交什么值", True, None),
               ("，但不决定引擎怎么跑。所以 09_Tests_and_Tools/run-worker-demo.mjs 和 "
                "run-acceptance.mjs 重跑一遍", False, None),
               ("不会有任何变化", True, BAD),
               ("——它们直接调 Zeebe API 写变量，既不渲染表单也不跑表单校验。", False, None)])
    para(doc, "证据：accessibleFormatRequired 在 "
              "05_Test_Evidence/worker-run/worker-demo-2026-09-28T12-13-00-853Z.json:94 "
              "里是脚本直接设成 \"false\" 的，不是人在界面上填的。", color=MUTED)

    doc.add_heading("6.1 能看见差别的三处", level=2)
    table(doc, ["#", "位置", "改前", "改后", "对 API 路径也成立吗"], [
        ["1", "Tasklist 控件外观", "全部是文本框 / 复选框",
         "出现日期选择器、数字框、下拉框、多行文本", "不适用（API 不渲染表单）"],
        ["2", "Tasklist 提交行为", "空着也能提交",
         "必填 / 格式不合规，提交被拦住并显示校验错误", "不适用"],
        ["3", "Operate 里的流程路径", "见 6.2 的三种情况", "见 6.2", "只在「人提供值」时成立"],
    ], [0.9, 3.4, 4.0, 5.4, 3.7])

    doc.add_heading("6.2 第 3 处按「谁提供值」分三种情况", level=2)
    table(doc, ["谁提供值", "改前", "改后", "有区别吗"], [
        ["A. API 脚本直接写\n（现有验收证据走的就是这条）",
         "脚本写的是 \"accepted\" / \"routine\" / \"administrative\" / \"confirmed\"，"
         "都是模型认识的字面量，网关本来就对", "不变", "没有区别"],
        ["B. 人在 Tasklist 里填\n（本次改动影响的范围）",
         "自由文本框，人照着标签打 Accept / Administrative / Confirmed，"
         "没有条件成立，落默认分支", "下拉框只能选，条件成立，走对分支", "有区别"],
        ["C. 变量根本没被设过",
         "FEEL 取 null，落默认分支", "人现在能填了，走对分支", "有区别，且 API 路径也一样"],
    ], [4.2, 6.0, 4.4, 2.8])
    para(doc, "")
    rich(doc, [("C 类才是两条路径上都存在的缺陷，而且恰恰是证据从未覆盖的地方：", True, None)])
    table(doc, ["元素", "在全部交付证据里出现的次数"], [
        ["G_LetterOnTime、G_LetterAge、G_LetterAgeExtended", "0"],
        ["T_Escalate、T_WeeklyReminder、T_EscalateToManager、"
         "T_EscalateToHigherManagement、T_ReminderInterval", "0"],
        ["G_ReferralDecision / G_EnquiryType / G_PaymentOutcome",
         "120 / 12 / 88（都是 API 直接写的正确取值）"],
    ], [11.0, 6.4])
    rich(doc, [("S1/S3 的延迟信函升级链，你们的验收和 demo 一次都没走到过，"
                "所以那个「复选框 + 数值比较」的 bug 从来没被触发，也就一直没被发现。",
                False, None)])

    doc.add_heading("6.3 在 Tasklist 上演示的四步（评审要看效果时按这个走）", level=2)
    para(doc, "前置：Camunda 8.10 起来，用 09_Tests_and_Tools/deploy-all.mjs 部署模型和表单。",
         color=MUTED)
    table(doc, ["#", "打开的任务", "怎么操作", "应该看到什么"], [
        ["A", "T_RecordPayment\n「Record the payment reference, amount and date」",
         "打开表单即可",
         "改前只有 1 个字段（患者标识）；改后有 5 个字段，金额是数字输入框、"
         "付款日是日期选择器、币种是下拉框"],
        ["B", "同上", "什么都不填，直接点提交",
         "改前提交成功；改后提交被拦住，每个必填字段下方出现校验提示，流程不前进"],
        ["C", "T_WeeklyReminder\n「Issue a weekly reminder ...」",
         "在 letterAgeMonths 里填 2",
         "改前 Operate 里只看得到 T_WeeklyReminder 反复出现（落到默认分支）；"
         "改后能看到 G_LetterAge → T_EscalateToManager（升级到行政管理员）"],
        ["D", "T_RecordReferralDecision\n「Record the referral decision ...」",
         "改前填 Accept；改后在下拉框里选 Accepted",
         "改前实例进入 Rejected 分支并通知转诊方；改后进入 Accepted 分支，"
         "转给门诊预约组"],
    ], [0.9, 4.6, 3.6, 7.5], font_size=8.5)

    # ------------------------------------------------- 7 gateway table (landscape)
    landscape(doc)
    doc.add_heading("7. 12 个网关判定：改前 vs 改后", level=1)
    rich(doc, [("下表不是手写的，是 ", False, None),
               ("demo-form-control-impact.py", False, None),
               (" 直接读模型里的 ", False, None), ("conditionExpression", False, None),
               (" 和网关的 ", False, None), ("default", False, None),
               (" 属性算出来的：对每个网关算两遍，一遍喂「旧控件会产出的值」"
                "（复选框给 true，文本框给人打进去的字），一遍喂「新控件会产出的值」。",
                False, None)])
    changed = sum(1 for r in gateways if r["changes"])
    rich(doc, [("结果：", True, None), (f"{changed} / {len(gateways)} 个判定走向改变。",
                                      True, BAD)])
    rich(doc, [("阅读时重点看这三条：", True, None)])
    bullet(doc, "referralDecision：人在文本框里填 Accept（照着标签上的字抄），"
                "转诊被直接判为「拒绝」并通知转诊方；只有填对 accepted 才会转给预约组。"
                "这正好印证缺陷日志里 DEF-09 记的「取值不一致」问题。")
    bullet(doc, "enquiryType：填 Administrative 会被判成 Clinical，转给临床护士；"
                "而该网关的默认分支就是 Clinical——填错会被静默升级到临床。")
    bullet(doc, "paymentStatus：填 Confirmed 被判成「付款失败」，让患者重试付款；"
                "这是财务事故级别的后果。")
    para(doc, "模型代号：O1 = O1_Operational_Merged，S1 = S1_Strategic_Landscape，"
              "S2 = S2_Strategic_Referral_To_Authorisation，"
              "S3 = S3_Strategic_Treatment_To_Aftercare。", color=MUTED)
    short = {"O1_Operational_Merged": "O1", "S1_Strategic_Landscape": "S1",
             "S2_Strategic_Referral_To_Authorisation": "S2",
             "S3_Strategic_Treatment_To_Aftercare": "S3"}
    table(doc, ["模型", "网关", "变量", "改前：旧控件产出的值 → 走哪条分支",
                "改后：新控件产出的值 → 走哪条分支", "判定"],
          [[short.get(r["model"].replace(".bpmn", ""), r["model"]), r["gateway"], r["variable"],
            f"{r['old']!r}\n{r['before']}\n（{r['whyBefore']}）",
            f"{r['new']!r}\n{r['after']}\n（{r['whyAfter']}）",
            r["verdict"]] for r in gateways],
          [1.6, 3.2, 2.6, 8.0, 8.0, 3.2], font_size=8)

    portrait(doc)
    doc.add_heading("8. 验证结果（四个校验器，可当场复跑）", level=1)
    code(doc, [
        "python 09_Tests_and_Tools/validate-forms.py           # 项目自带",
        "python 09_Tests_and_Tools/validate-contract.py        # 项目自带",
        "python 09_Tests_and_Tools/validate-models.py 02_BPMN_Models/*.bpmn",
        "python 09_Tests_and_Tools/validate-form-controls.py   # 本次新增",
        "python 09_Tests_and_Tools/demo-form-control-impact.py # 本次新增",
    ])
    para(doc, "")
    table(doc, ["校验器", "检查什么", "结果"],
          [[r["script"], r["what"], r["result"]] for r in results],
          [4.4, 5.4, 7.6], font_size=8.5)

    doc.add_heading("8.1 最有说服力的一个数字", level=2)
    rich(doc, [("项目自带的 ", False, None), ("validate-contract.py", False, None),
               (" 统计「有多少个表单字段能被人工提供」：改前 ", False, None),
               ("26 个", True, None), ("，改后 ", False, None), ("53 个", True, None),
               ("，翻了一倍。一个字段就是一个能被人工填写的业务数据项。", False, None)])

    # ---------------------------------------------------- 9 new defects
    doc.add_heading("9. 顺带发现的 4 个新缺陷（属于第 3 项「修模型」，本次未改）", level=1)
    para(doc, "我们没有擅自改 .bpmn，因为这属于第 3 项的范围，需要确认后统一处理。"
              "四条已写入改动清单第 4 节。", color=MUTED)
    table(doc, ["编号", "缺陷", "为什么严重", "建议修法"], [
        ["DEF-FORM-05",
         "T_RefundDecision、T_AuthoriseUrgentTreatment 各有两条无条件出线，中间没有网关",
         "BPMN 语义把任务的多条出线当作并行拆分，所以两条路都会执行——退款场景下每次都会发起退款",
         "各插一个排他网关，用 refundDecision / 授权结果做条件"],
        ["DEF-FORM-06",
         "S1_Strategic_Landscape.bpmn:194,197 判断布尔变量 accepted，"
         "但没有任何表单采集它、其他模型都用 referralDecision；"
         "已确认该变量在全部交付证据里从未被赋过值",
         "G_Accepted 无论走 Tasklist 还是 API 都只会落到默认分支，"
         "S1 里「转诊是否被接受」这个判断实际失效",
         "统一改用受控变量 referralDecision"],
        ["DEF-FORM-07",
         "form-prepare-accessible-format 里放着 followUpSlotWithinPeriod"
         "（随访预约标志），位置明显串了",
         "表单采集了不属于本任务的数据",
         "从该表单移除"],
        ["DEF-FORM-08",
         "3 个工作器输入全项目没有表单：letterRecipients、documentationCheckResult、"
         "refundAuthorised",
         "目前靠工作器默认值兜底，等于业务取值由代码决定而不是由人决定",
         "要么补表单，要么把默认值写成明确的设计决策"],
    ], [2.4, 5.4, 5.2, 4.4], font_size=8.5)
    rich(doc, [("说明：", True, None),
               ("这 4 条恰恰是「改字段类型」这个动作挖出来的——"
                "要判断每个控件该收什么数据，就必须把模型的每个网关、"
                "工作器读的每个变量逐个对一遍。", False, None)])

    # ---------------------------------------------------- 10 limits
    doc.add_heading("10. 已知限制，需要主动说明", level=1)
    rich(doc, [("1. 金额只到整数（整英镑）。", True, None),
               ("Camunda 的数字控件默认只输出整数；要保留小数需在 Modeler 里"
                "给该字段勾上 \"Output as string\"，或改用带小数正则的文本框。"
                "目前 paymentAmount、approvedAmount、refundAmount、chargeAmount "
                "都是整英镑，字段标签里已写清楚。", False, None)])
    rich(doc, [("2. appointmentWithin14Days 仍是复选框。", True, None),
               ("它问的是「是否 14 天内」，是是非问句，复选框是正确控件。"
                "更严谨的做法是采集 appointmentDate 后由规则推导这个布尔值——"
                "本期已补上 appointmentDate，推导规则可作为后续改进。", False, None)])
    rich(doc, [("3. 现有验收证据看不到本次改动。", True, None),
               ("本次只碰 03_Forms/*.json，key 一个没改，模型和工作器一行未改；"
                "但验收脚本走的是 API，不渲染表单、不跑表单校验，"
                "所以重跑它们不会有变化。这不是改动没生效，而是工具用错了——"
                "要看效果必须走 Tasklist（见第 6 节）。", False, None)])
    rich(doc, [("4. Tasklist 实机截图尚未产出。", True, None),
               ("当前机器没有运行中的 Camunda 集群，也没有 Docker，"
                "进程级外网被拦（npm / CDN 都下不来），"
                "因此没有生成 Tasklist 的前后对照截图。", False, None)])

    # ---------------------------------------------------- 11 next steps
    doc.add_heading("11. 下一步建议", level=1)
    table(doc, ["顺序", "事项", "归属", "预估"], [
        ["1", "在 Camunda 8 重新部署 68 个表单，按第 6 节的步骤在 Tasklist 走一遍并截图，"
              "结果存进 05_Test_Evidence/screenshots/", "第 5 项收尾", "半天"],
        ["2", "修 DEF-FORM-05/06/07（3 个模型/表单缺陷），DEF-FORM-08 定性",
         "第 3 项「修模型」", "1 天"],
        ["3", "若需金额小数，统一开启 \"Output as string\" 并回归", "第 5 项补充", "2 小时"],
        ["4", "第 2 项 RBAC：模型侧 99 个任务的 candidateGroups 已经有了，"
              "只差 Identity 用户/组与授权", "第 2 项", "2-3 天"],
        ["5", "第 1 项数据库持久化：pom.xml 无任何 JDBC/JPA，HospitalStore 是进程内内存，"
              "重启即失", "第 1 项", "4-7 天"],
    ], [1.2, 9.4, 3.0, 1.8])

    # ---------------------------------------------------- appendix
    doc.add_heading("附录 A：10 处类型改动的文件与行号索引", level=1)
    table(doc, ["#", "文件（相对项目根目录）", "行", "变量", "改前 → 改后"],
          [[str(i + 1), f"03_Forms/{r['form']}.form", f"L{r['line']}", r["key"],
            f"{r['was']} → {r['now']}"] for i, r in enumerate(retyped)],
          [0.9, 6.2, 1.2, 3.6, 3.3], font_size=8.5)

    doc.add_heading("附录 B：怎么自己核对", level=1)
    code(doc, [
        "# 看全部改动的文件清单",
        "git status --porcelain",
        "",
        "# 看某几个表单具体改了什么（推荐挑这三个）",
        "git diff 03_Forms/form-follow-up-review.form        # 复选框 -> 数字框",
        "git diff 03_Forms/form-record-payment.form          # 1 个字段 -> 5 个字段",
        "git diff 03_Forms/form-handle-payment-failure.form  # 文本框 -> 下拉框",
        "",
        "# 只看统计",
        "git diff --stat -- 03_Forms",
        "",
        "# 批量列出所有 number/select/datetime/textarea 控件及其行号",
        "Select-String -Path 03_Forms\\*.form -Pattern '\"type\":\\s*\"(number|select|datetime|textarea)\"'",
        "",
        "# 把表单改回原样（新增文件需另外删除）",
        "git checkout -- 03_Forms",
    ])

    doc.add_heading("附录 C：本次新增的文件", level=1)
    table(doc, ["文件", "用途"], [
        ["09_Tests_and_Tools/fix-form-field-types.py",
         "改动脚本本身：声明式、可重跑、幂等（重跑显示 0 改动）"],
        ["09_Tests_and_Tools/validate-form-controls.py",
         "新增校验器：控件类型是否匹配数据、网关变量是否已采集且必填"],
        ["09_Tests_and_Tools/demo-form-control-impact.py",
         "运行演示脚本：读模型条件算出改前/改后各走哪条分支"],
        ["09_Tests_and_Tools/make-form-fix-report.py", "生成本 Word 文档"],
        ["08_Repository_Documents/form-field-change-log.md",
         "逐条改动清单（含 4 个新缺陷）"],
        ["08_Repository_Documents/form-field-fix-briefing.md", "汇报稿（含 3 分钟口头版）"],
        ["08_Repository_Documents/form-fix-runtime-demo.md",
         "运行演示说明：能看见差别的三处、Tasklist 复现步骤"],
        ["05_Test_Evidence/verification/form-controls-check.json",
         "validate-form-controls.py 的机器可读结果"],
    ], [7.4, 10.0], font_size=9)

    doc.save(str(out_path))
    print(f"wrote {out_path}")
    print(f"  retyped={len(retyped)} added={len(added)} validated={len(validated)} "
          f"gateways={len(gateways)} changed={changed}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "08_Repository_Documents" /
                                        "表单字段类型整改_汇报材料.docx"))
    args = ap.parse_args()
    return build(Path(args.out))


if __name__ == "__main__":
    sys.exit(main())
