#!/usr/bin/env python3
"""Build the four-person defence crib sheet, English and Chinese paired.

One page per person: what they own, what was wrong, what changed (with the file and line
they can open), how to show it, the evidence, and the answer to the likely question. The
English is deliberately simple - short sentences, everyday words - because it has to be
read aloud. Every English line is followed by its Chinese.

Laid out as paragraphs, not a table: a two-column table lets a long unbreakable file name
widen its column and push the other one off the page, and this is a sheet to read from, so
wrapping text is what is wanted.

usage: python make-defence-script.py
"""

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "08_Repository_Documents" / "答辩讲稿_四人分讲_中英对照.docx"

EN_FONT = "Calibri"
ZH_FONT = "微软雅黑"
NAVY = RGBColor(0x1F, 0x38, 0x64)
ZH_COLOUR = RGBColor(0x33, 0x33, 0x33)

PAGES = [
    (
        "Part 1 - Max: Fix the BPMN model",
        "第 1 部分 - Max：修复 BPMN 模型",
        [
            ("My job", "我负责", "head"),
            ("I work on the BPMN model.", "我负责 BPMN 模型。", "body"),
            ("The model shows how the hospital works.", "模型画出医院的工作流程。", "body"),
            ("Some parts were wrong. I fixed them.", "有些地方是错的，我把它们修好了。", "body"),

            ("What was wrong", "原来哪里不对", "head"),
            ("One task had two lines out. There was no rule. So both lines ran.",
             "有一个任务有两条出线，却没有条件，所以两条路都会走。", "body"),
            ("This was the refund task. So every refund case also kept the money.",
             "这就是退款那个任务。结果每个退款单同时也保留了钱。", "body"),
            ("Another task also had two lines out. Here both lines should run, but nobody could see that.",
             "另一个任务也有两条出线。这里两条本来就都该走，但没有人看得出来。", "body"),
            ("In model S1, a gate looked at a word that nobody wrote. So it never worked.",
             "在 S1 模型里，一个网关看的是一个没人写过的变量，所以它一直不生效。", "body"),
            ("One form asked the wrong question. Three answers had no form at all.",
             "有一个表单问了不属于它的问题。还有三个答案根本没有表单可填。", "body"),

            ("What I changed", "我改了什么", "head"),
            ("I put a gate in the middle. Now it must pick one line.",
             "我在中间加了一个网关。现在它必须选一条路。", "body"),
            ("File S3_Strategic_Treatment_To_Aftercare.bpmn, line 432 and line 639.",
             "文件 S3_Strategic_Treatment_To_Aftercare.bpmn，第 432 行和第 639 行。", "body"),
            ("I put in a clear 'both' gate. Now everyone can see both lines run.",
             "我加了一个明确的“两条都走”网关，现在一眼就能看出两条都要走。", "body"),
            ("File O1_Operational_Merged.bpmn line 515. File S3 line 216.",
             "文件 O1_Operational_Merged.bpmn 第 515 行。S3 第 216 行。", "body"),
            ("S1 now uses a word that a form really writes.",
             "S1 现在改用一个表单真的会写的变量。", "body"),
            ("File S1_Strategic_Landscape.bpmn line 194 and line 55.",
             "文件 S1_Strategic_Landscape.bpmn 第 194 行和第 55 行。", "body"),
            ("I moved the wrong question out, and gave the three answers their own forms.",
             "我把那个错的问题移走，并给那三个答案各自加了表单。", "body"),

            ("How to show it (30 seconds)", "现场怎么演示（30 秒）", "head"),
            ("Open S3 and go to line 432. Say: before, two lines ran; now a gate picks one.",
             "打开 S3 跳到第 432 行。说：以前两条路都走，现在网关选一条。", "body"),
            ("Then show O1 line 515 and say why here both lines must run.",
             "再展示 O1 第 515 行，说明为什么这里两条都必须走。", "body"),
            ("The models are already on the server: O1 v12, S1 v5, S3 v5.",
             "模型已经部署到服务器：O1 v12、S1 v5、S3 v5。", "body"),

            ("Proof", "证据", "head"),
            ("The model checker says clean. Before, it found 9 problems.",
             "模型校验器显示 clean。修之前它有 9 个问题。", "body"),
            ("The form checker found 4 model problems. Now 0.",
             "表单校验器发现 4 个模型缺陷，现在是 0。", "body"),
            ("See defect-log.md, group D (DEF-17 to DEF-21).",
             "见 defect-log.md 的 D 组（DEF-17 到 DEF-21）。", "body"),

            ("If the teacher asks", "老师问就答", "head"),
            ("Why one gate here, but a 'both' gate there?",
             "为什么这里用一个网关，那里却用“两条都走”的网关？", "body"),
            ("The case study says the money is either refunded or kept. Pick one.",
             "案例研究说：钱要么退，要么留。只能选一个。", "body"),
            ("The case study says the patient still gets care, AND the reason goes to Finance. Both.",
             "案例研究说：病人照样治疗，同时理由要交给财务。两个都要。", "body"),
        ],
    ),
    (
        "Part 2 - Peter: The forms",
        "第 2 部分 - Peter：表单",
        [
            ("My job", "我负责", "head"),
            ("I work on all 69 forms. A form is the page a worker fills in.",
             "我负责全部 69 个表单。表单就是员工填写的那个页面。", "body"),

            ("What was wrong", "原来哪里不对", "head"),
            ("We used only two kinds of box: a text box and a tick box.",
             "我们只用了两种控件：文本框和复选框。", "body"),
            ("A date? A text box. A number? A text box.",
             "日期用文本框，数字也用文本框。", "body"),
            ("One number was a tick box.", "有一个数字用的是复选框。", "body"),
            ("A tick box gives true or false. The gate asks: is the number 7 or less?",
             "复选框给出的是 true 或 false。而网关问的是：这个数字小于等于 7 吗？", "body"),
            ("True is not a number. So the gate never worked the right way.",
             "true 不是数字。所以这个网关一直不对。", "body"),
            ("Nobody had to fill anything. You could send an empty form.",
             "没有任何框是必须填的，可以提交一张空白表单。", "body"),
            ("Three answers had no box at all.", "有三个答案根本没有框可以填。", "body"),

            ("What I changed", "我改了什么", "head"),
            ("Now we use 6 kinds of box.", "现在我们用了 6 种控件。", "body"),
            ("4 tick boxes became number boxes.",
             "4 个复选框改成了数字框。", "body"),
            ("File form-deliver-treatment-cycle.form: key on line 14, type=number on line 16.",
             "文件 form-deliver-treatment-cycle.form：key 在第 14 行，type=number 在第 16 行。", "body"),
            ("6 text boxes became drop-down lists.",
             "6 个文本框改成了下拉框。", "body"),
            ("Files form-clinical-review-referral.form and 5 more, line 14 to line 16.",
             "文件 form-clinical-review-referral.form 等 6 个，第 14 行到第 16 行。", "body"),
            ("Now 162 boxes have rules. 157 must be filled, 70 check the format.",
             "现在有 162 个框带校验规则，其中 157 个必填、70 个校验格式。", "body"),
            ("All 69 forms check the patient number.",
             "69 个表单全部校验患者编号。", "body"),
            ("File form-receive-referral.form, line 22 to line 27.",
             "文件 form-receive-referral.form，第 22 到 27 行。", "body"),
            ("All 25 gate words now have a box, and must be filled.",
             "25 个网关变量现在都有框，而且都是必填。", "body"),

            ("How to show it (30 seconds)", "现场怎么演示（30 秒）", "head"),
            ("Open form-deliver-treatment-cycle.form, lines 14 to 21.",
             "打开 form-deliver-treatment-cycle.form，第 14 到 21 行。", "body"),
            ("You can see key, label, type=number and the rules on one screen.",
             "一屏就能看到 key、label、type=number 和校验规则。", "body"),
            ("Then open that task in Tasklist. You see a number box, not a tick box.",
             "再在 Tasklist 打开那个任务，看到的是数字框，不是复选框。", "body"),
            ("Send an empty form. It is blocked.",
             "提交一张空白表单，会被直接拦住。", "body"),

            ("Proof", "证据", "head"),
            ("validate-forms.py: clean.", "validate-forms.py：clean。", "body"),
            ("validate-form-controls.py: clean, 0 problems.",
             "validate-form-controls.py：clean，0 个问题。", "body"),
            ("See form-field-change-log.md.", "见 form-field-change-log.md。", "body"),

            ("If the teacher asks", "老师问就答", "head"),
            ("Why is an empty box dangerous?", "为什么空着不填反而危险？", "body"),
            ("A form sends every box it shows. An empty box erases the old value.",
             "表单会提交它显示的每一个框。空框会把原来的值清掉。", "body"),
            ("Why check the format, not only 'must fill'?",
             "为什么除了必填还要校验格式？", "body"),
            ("The patient number joins records together. A wrong format breaks that join.",
             "患者编号要用来串联各个系统，格式错了就关联不上。", "body"),
        ],
    ),
    (
        "Part 3 - Henry: Who can see what (RBAC)",
        "第 3 部分 - Henry：角色权限（RBAC）",
        [
            ("My job", "我负责", "head"),
            ("I work on the rules and the proof.", "我负责规则和证据。", "body"),
            ("The teacher asked: different people should see different tasks.",
             "老师要求：不同的人应该看到不同的任务。", "body"),

            ("What I found", "我发现了什么", "head"),
            ("First I checked. Was it working? No.",
             "我先去验证。它生效了吗？没有。", "body"),
            ("In the server settings, permission checks were OFF.",
             "服务器配置里，权限检查是关着的。", "body"),
            ("So every person could see every task.",
             "所以每个人都能看到所有任务。", "body"),
            ("'Different people see different tasks' was not true at all.",
             "“不同角色看到不同任务”当时根本不成立。", "body"),

            ("What I changed", "我改了什么", "head"),
            ("I turned the permission checks ON.", "我把权限检查打开了。", "body"),
            ("File c8run configuration application.yaml - two lines.",
             "文件 c8run 的 configuration/application.yaml - 改了两行。", "body"),
            ("I made 10 groups and 10 users. Each user is in one group only.",
             "我建了 10 个组和 10 个用户，每个用户只在一个组里。", "body"),
            ("Every task already says which group owns it: 99 places in the model.",
             "模型里每个任务本来就写了属于哪个组，一共 99 处。", "body"),
            ("Files setup-rbac.py and verify-rbac.py.",
             "文件 setup-rbac.py 和 verify-rbac.py。", "body"),

            ("How to show it (30 seconds)", "现场怎么演示（30 秒）", "head"),
            ("Run: python 09_Tests_and_Tools/verify-rbac.py",
             "运行：python 09_Tests_and_Tools/verify-rbac.py", "body"),
            ("A: all 10 users are in the right group. 10 of 10.",
             "A：10 个用户都在正确的组里，10/10。", "body"),
            ("B: a user with no rights sees 0 tasks. A user with rights sees 785.",
             "B：没有任何权限的用户看到 0 条，有权限的用户看到 785 条。", "body"),
            ("C: each group sees only its own tasks. 0 mistakes.",
             "C：每个组只看到自己的任务，0 处错配。", "body"),
            ("Then open Tasklist. Log in as secretary.demo, then as finance.demo. The lists differ.",
             "再打开 Tasklist，分别用 secretary.demo 和 finance.demo 登录，两个列表不一样。", "body"),

            ("Proof", "证据", "head"),
            ("See 05_Test_Evidence/rbac/task-visibility.json and rbac-setup.md.",
             "见 05_Test_Evidence/rbac/task-visibility.json 和 rbac-setup.md。", "body"),

            ("If the teacher asks", "老师问就答", "head"),
            ("How do you know it is not still showing everything?",
             "你怎么知道它不是照样显示全部？", "body"),
            ("We made one user with no rights at all. He sees 0 tasks.",
             "我们特意建了一个完全没有权限的用户，他搜出来是 0 条。", "body"),
            ("Where are the pictures?", "截图呢？", "body"),
            ("Tasklist uses a login page, so a robot browser cannot get in. We take the two pictures by hand.",
             "Tasklist 用的是登录页面，自动浏览器进不去，两张截图需要人工截。", "body"),
            ("Did turning it on break anything?", "打开权限有没有弄坏别的东西？", "body"),
            ("Yes, and it was quiet. The workers stopped getting jobs, with no error. We found it and fixed it.",
             "有，而且很隐蔽：工作者收不到作业却不报错。我们定位到并用 BasicAuthInterceptor.java 修好了。", "body"),
        ],
    ),
    (
        "Part 4 - Finn: Save the data in a database",
        "第 4 部分 - Finn：把数据存进数据库",
        [
            ("My job", "我负责", "head"),
            ("I work on the workers' memory.", "我负责工作器的状态存储。", "body"),
            ("The teacher asked: save the business data in a database.",
             "老师要求：把业务数据保存进数据库。", "body"),

            ("What was wrong", "原来哪里不对", "head"),
            ("The data lived only inside the program.",
             "数据只存在程序里面。", "body"),
            ("If the program stopped, all the data was gone.",
             "程序一停，数据就全没了。", "body"),
            ("Our own code said: 'It is not a database. Nothing survives a restart.'",
             "我们自己的代码里就写着：“这不是数据库，重启后什么都不剩。”", "body"),

            ("What I changed", "我改了什么", "head"),
            ("I added a real database. It is called H2, and it has 4 tables.",
             "我接入了真正的数据库，叫 H2，一共有 4 张表。", "body"),
            ("Table 1: the business records.", "表 1：业务记录。", "body"),
            ("Table 2: the appointments. It stops the same appointment being booked twice.",
             "表 2：预约。它能防止同一个预约被确认两次。", "body"),
            ("Table 3: the retry counts.", "表 3：重试次数。", "body"),
            ("Table 4: the audit log. It can only add. It can never change.",
             "表 4：审计日志。只能追加，永远不能修改。", "body"),
            ("I did not change any worker. The outside of the code is the same.",
             "我没有改动任何工作器，代码对外的样子完全一样。", "body"),
            ("Files Database.java (new), HospitalStore.java, OperationsLog.java.",
             "文件 Database.java（新增）、HospitalStore.java、OperationsLog.java。", "body"),

            ("How to show it (30 seconds)", "现场怎么演示（30 秒）", "head"),
            ("Run the write command. Then run the read command.",
             "先运行写入命令，再运行读取命令。", "body"),
            ("These are two different programs. The first one is already closed.",
             "这是两个不同的程序，第一个已经关闭了。", "body"),
            ("The second one reads all 7 things. 7 of 7 pass.",
             "第二个程序读到了全部 7 项，7/7 通过。", "body"),
            ("So the data did not die.", "所以数据没有丢。", "body"),

            ("Proof", "证据", "head"),
            ("See 05_Test_Evidence/persistence/run-1-write.txt and run-2-read.txt.",
             "见 05_Test_Evidence/persistence/run-1-write.txt 和 run-2-read.txt。", "body"),
            ("The 41 unit tests still pass.", "41 个单元测试仍然全部通过。", "body"),
            ("See database-integration.md.", "见 database-integration.md。", "body"),

            ("If the teacher asks", "老师问就答", "head"),
            ("Is the data really safe?", "数据真的不丢吗？", "body"),
            ("Yes. Two programs. One writes and closes. The other reads everything.",
             "是的。两个程序，一个写完就关，另一个全部读到。", "body"),
            ("But say this as well, do not hide it:", "但也要主动说，不要掩盖：", "note"),
            ("On this laptop a restarted worker cannot write again, because the sandbox blocks the database file lock. On a normal computer this does not happen, and we wrote it down.",
             "在这台笔记本上，重启后的工作器无法再写，因为沙箱拦住了数据库文件锁。普通电脑上不会这样。我们已经把这个写进了文档。", "body"),
        ],
    ),
]

CLOSING = [
    ("Say this together at the end", "最后四个人一起说这一句", "head"),
    ("Of the 5 items, 4 already have full running proof. Item 3 has three checks: the checker, the deployment and a real run.",
     "5 项里 4 项已有完整运行证据。第 3 项有三重复核：校验器、部署、真实运行。", "body"),
    ("One thing is not finished yet, and we say so: the 18 acceptance cases were run on 27 September, on the old 68 forms.",
     "还有一件事没做完，我们如实说明：18 个验收用例是 9 月 27 日在旧版 68 个表单上跑的。", "body"),
    ("We have to run them again. The tool is ready and it is one command.",
     "我们需要重跑一次。工具已经写好，只要一条命令。", "body"),
]


def style_run(run, zh=False, size=9, bold=False, colour=None):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = ZH_FONT if zh else EN_FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), ZH_FONT)
    run.font.color.rgb = colour or (ZH_COLOUR if zh else RGBColor(0, 0, 0))


def add_person(document, title_en, title_zh, rows):
    p = document.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(3)
    style_run(p.add_run(title_en + "   "), size=12, bold=True, colour=NAVY)
    style_run(p.add_run(title_zh), zh=True, size=11.5, bold=True, colour=NAVY)

    for en, zh, kind in rows:
        para = document.add_paragraph()
        if kind == "head":
            para.paragraph_format.space_before = Pt(3)
            para.paragraph_format.space_after = Pt(0)
            style_run(para.add_run(en + "   "), size=10, bold=True, colour=NAVY)
            style_run(para.add_run(zh), zh=True, size=10, bold=True, colour=NAVY)
        else:
            para.paragraph_format.space_before = Pt(0)
            para.paragraph_format.space_after = Pt(0.5)
            para.paragraph_format.left_indent = Cm(0.4)
            style_run(para.add_run(en + "　"), size=9, bold=(kind == "note"))
            style_run(para.add_run(zh), zh=True, size=9, bold=(kind == "note"))


def build():
    document = Document()
    section = document.sections[0]
    section.page_height = Cm(29.7)
    section.page_width = Cm(21.0)
    for attr in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(section, attr, Cm(1.2))

    head = document.add_paragraph()
    head.alignment = WD_ALIGN_PARAGRAPH.CENTER
    head.paragraph_format.space_after = Pt(2)
    style_run(head.add_run("Group 17 - Review List: Four-Person Defence Script"),
              size=13, bold=True, colour=NAVY)
    head2 = document.add_paragraph()
    head2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    head2.paragraph_format.space_after = Pt(5)
    style_run(head2.add_run("17 组整改清单：四人分讲稿（中英对照，一人一页）"),
              zh=True, size=11, bold=True, colour=NAVY)

    for i, (title_en, title_zh, rows) in enumerate(PAGES):
        if i > 0:
            brk = document.add_paragraph()
            brk.paragraph_format.space_before = Pt(0)
            brk.paragraph_format.space_after = Pt(0)
            brk.add_run().add_break(WD_BREAK.PAGE)
        add_person(document, title_en, title_zh, rows)

    brk = document.add_paragraph()
    brk.paragraph_format.space_before = Pt(0)
    brk.paragraph_format.space_after = Pt(0)
    brk.add_run().add_break(WD_BREAK.PAGE)
    add_person(document, CLOSING[0][0], CLOSING[0][1], CLOSING[1:])

    document.save(str(OUT))
    lines = sum(len(p[2]) for p in PAGES) + len(CLOSING) - 1
    print(f"wrote {OUT}")
    print(f"  {len(PAGES)} people + 1 closing page, {lines} paired lines")


if __name__ == "__main__":
    build()
