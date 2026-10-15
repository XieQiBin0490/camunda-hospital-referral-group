# i* 重画流程（SD + SR）

> 用途：把 i\* 战略依赖（SD）和战略理由（SR）两张图做到符合作业要求。
> 数据全部从 `06_iStar_Models/iStar_models_source.json` 生成，与模型一致。
> 可导入 piStar 的工程文件：`06_iStar_Models/pistar/iStar_SD_pistar.json` 和 `iStar_SR_pistar.json`。

---

## 0. 先决定：要不要重画

**先看清楚你手上是哪一版。** 仓库里已经有一套成品，和作品集正文的数字完全对得上：

| | 早期草稿（6 个 actor 的 piStar 截图那一版） | 仓库里的成品 `06_iStar_Models/` |
| --- | --- | --- |
| SD | 6 个 actor、约 11 条依赖 | **16 个 actor、40 条 typed dependency** |
| SR | 一个 "Specialist Hospital" 边界 | **7 个 actor 打开、61 个 intentional element、9 条 boundary dependency** |
| 与作品集正文一致？ | 对不上 | 一致（正文写的正是这些数字） |

**结论：如果只是担心图不够好，那不用重画——仓库里这套是符合作业要求的。**
真正的问题是 `tools/build-istar.mjs` 生成器不在仓库里，所以没法重新导出。下面的流程就是解决这个：
用 piStar（i\* 2.0 的参考工具）打开我导出的工程文件，补上内部链接，再导出 PDF/SVG。

---

## 1. 作业到底要求什么

Task 02 原文（Portfolio 规格 Section 2）：

> Develop both an i\* Strategic Dependency (SD) model and a Strategic Rationale (SR) model for the
> initial release. Identify actors, goals, soft goals, tasks, resources and dependencies as appropriate.
> **Explain important modelling choices and assumptions, keeping the SD and SR models consistent.**

i\* 这一项占 **20%**，评分标准 70%+ 那一档要求：

> Comprehensive, precise SD and SR models show deep understanding of stakeholder dependencies and
> rationale. **Assumptions, goal relationships and limitations are critically justified.**

交付物要求：`SD and SR diagrams as readable PDF exports, **with editable source files where supported**`。

**所以图必须做到四件事：** ①元素和链接类型用对；②SD 和 SR 互相一致；③假设与取舍有说明；④除了 PDF 还要交可编辑源文件。

---

## 2. i\* 2.0 记法规则（图画错基本都是这里错）

| 元素 | 形状 | piStar 里的类型名 |
| --- | --- | --- |
| Actor（含 Agent / Role） | 圆或圆角框，带名字 | `istar.Actor` / `istar.Agent` / `istar.Role` |
| Goal | **圆角矩形** | `istar.Goal` |
| Task | **六边形** | `istar.Task` |
| Resource | **矩形** | `istar.Resource` |
| Soft goal | **云形** | `istar.Quality`（i\* 2.0 把 soft goal 叫 Quality） |

| 链接 | 画法 | piStar 里的类型名 |
| --- | --- | --- |
| 任务分解 Task decomposition | 父任务 → 子元素，父端有 **AND 横杠** | `istar.AndRefinementLink` / `istar.OrRefinementLink` |
| Means-end | 手段（任务/资源）→ 目的（goal/soft goal），**空心箭头**指向目的 | `istar.OrRefinementLink`（piStar 用 refinement 表达） |
| 贡献 Contribution | 指向 soft goal，线上标 `make` / `help` / `hurt` / `break` / `some+` / `some-` | `istar.ContributionLink` + `label` |
| 依赖 Dependency | **虚线**，中间是 dependum 形状，两端连 depender 和 dependee | `istar.DependencyLink`（两条：depender→dependum→dependee） |

> 常见错误：把 task 画成矩形、把 resource 画成圆角矩形、contribution 不标 help/hurt、
> 依赖用实线、dependent 只连一条 DependencyLink。这些在 piStar 里都会直接体现在导出图上。

---

## 3. 操作流程

### 步骤 1：打开 piStar

浏览器打开 <https://istar.rwth-aachen.de/>（或者本地跑 `jhcp/piStar`）。

### 步骤 2：导入 SD 工程

`File → Load`，选 `06_iStar_Models/pistar/iStar_SD_pistar.json`。

导入后应该有 **16 个 actor**（其中外部服务是 dependee only）、**40 个 dependum**、**80 条 DependencyLink**。

SD 的依赖关系全部来自模型，**不需要你再画任何链接**；只需要调整布局：把医院内部的 actor 放左侧，
外部 actor 放右侧，dependum 摆在两者之间，避免线交叉。

### 步骤 3：导入 SR 工程

`File → Load`，选 `06_iStar_Models/pistar/iStar_SR_pistar.json`。

导入后应该有 **7 个打开（展开）的 actor**、**61 个 intentional element**（形状和类型已经对）、**9 条 boundary dependency**，外部 actor 是折叠状态。

### 步骤 4：补 SR 的内部链接（**这一步必须手画**）

`iStar_models_source.json` 只记录了元素的类型和网格位置，**没有记录内部链接**——
那些链接只存在于 SVG 的线条里。所以 SR 的内部链接要在 piStar 里补，按下面三层规则：

**第 1 层：任务分解（AND）。** 每个 actor 里第 0 行那个横跨整行的任务（span=3）是父任务，
用 `AndRefinementLink` 连到第 1 行的各个 goal。箭头从父任务指向子 goal。

**第 2 层：means-end。** 第 2、3 行的 task，各自用 refinement 连到它实现的第 1 行 goal。
列对齐关系就是它服务的 goal（同列优先）。

**第 3 层：贡献链接（9 条，作品集正文里逐条写了，照抄）**

| Actor | 来源元素 | 目标（soft goal） | label | 正文里的解释 |
| --- | --- | --- | --- | --- |
| Consultant / Clinical Team | Record decision, rationale and clinician | Clinical accountability maintained | `help` | no administrative task has a means-end path to that soft goal, which is why clinical authority cannot be delegated |
| Medical Secretaries | Perform administrative checks and confirm recipients | No clinical judgement by administrative staff | `make` |  |
| Medical Secretaries | Request missing documentation | Referral administration kept proportionate | `hurt` | the honest modelling of a real trade-off |
| Outpatient Bookings Team | Validate the booking request and its urgency | Never booked silently outside the clinical period | `help` |  |
| Treatment & Chemotherapy Bookings Team | Keep the booking pending and record the retry | No duplicate appointments created | `make` |  |
| Finance Team | Send the secure payment request | Patient is never charged twice | `hurt` | deliberate: the model evidence for the rule that a payment whose confirmation is lost is marked for investigation rather than re-requested |
| Finance Team | Send the secure payment request | No unnecessary financial data stored | `make` |  |
| Patient Pathway Coordinators | Escalate after one month and after three months | Escalation proportionate, not repetitive | `hurt` | escalation is necessary but has a cost |
| Clinical Nurse Specialist Team | Answer clinical enquiries referred by call handlers | No clinical advice from non-clinical staff | `make` |  |

> 注意第 6、7 条：**同一个任务 `Send the secure payment request` 同时 hurt 一个 soft goal、make 另一个**。
> 这个负向贡献是整张 SR 最有分析价值的地方（正文原话：payment 确认丢失时应该标记调查而不是重复扣款），
> 重画时千万不要漏掉或改成 help。

### 步骤 5：检查一致性（作业明确要求）

规格原文要求 `keeping the SD and SR models consistent`，你们自己的作品集也列了一致性检查（B.5）：

1. SR 里打开的每个 actor，都必须在 SD 里出现。
2. SR 的每条 boundary dependency，都必须在 SD 里有对应的一条依赖，且类型相同。
3. SD 里用到的依赖类型，SR 的边界链接不能出现 SD 里没有的类型。
4. 每个 boundary link 的 dependum 名字，要和 SD 里那条依赖的 label 一致。

> 已知的一处名字不一致：SD 写的是 `Referring Organisation (GP or **other** hospital)`，
> SR 图里写的是 `GP or **another** hospital`。**统一成同一个写法**，否则第 4 条检查会挂。

### 步骤 6：导出

| 导出内容 | piStar 操作 | 放到哪 | 文件名 |
| --- | --- | --- | --- |
| SD 的 PDF | `File → Export → PDF` | `06_iStar_Models/` | `iStar_SD_Initial_Release.pdf` |
| SD 的可编辑源 | `File → Save` | `06_iStar_Models/pistar/` | `iStar_SD_pistar.json` |
| SR 的 PDF | `File → Export → PDF` | `06_iStar_Models/` | `iStar_SR_Initial_Release.pdf` |
| SR 的可编辑源 | `File → Save` | `06_iStar_Models/pistar/` | `iStar_SR_pistar.json` |

再补 PNG/SVG（piStar 的 `Export → PNG/SVG`），命名沿用现有的 `iStar_SD_Initial_Release.png/.svg`。

### 步骤 7：图和文档的数字要对上

作品集 `..._01_Task01_02_Strategic_BPMN_and_iStar.docx` 里写着：

- B.2：`The SD model contains 16 actors and 40 dependencies`
- B.3 / Figure 6：`seven actors, 61 intentional elements, 56 internal links, 9 boundary dependencies`

**重画之后回去核这几个数字。** 如果 SR 的内部链接数不是 56，要么补齐，要么把正文里的 56 改成实际数字——
两者不一致是评审最容易抓的地方。

---

## 4. 数据包：SD 的 16 个 actor

| # | Actor | 类别 |
| --- | --- | --- |
| 3 | Medical Secretaries | hospital actor |
| 4 | Consultant / Clinical Team | hospital actor |
| 5 | Clinical Nurse Specialist Team | hospital actor |
| 6 | Patient Pathway Coordinators | hospital actor |
| 7 | Outpatient Bookings Team | hospital actor |
| 8 | Treatment & Chemotherapy Bookings Team | hospital actor |
| 9 | Call Handling Team | hospital actor |
| 10 | Finance Team | hospital actor |
| 16 | Hospital Management Team | hospital actor |
| 1 | Patient / Authorised Representative | external actor (dependee only) |
| 2 | Referring Organisation (GP or other hospital) | external actor (dependee only) |
| 11 | External Scheduling Service | external actor (dependee only) |
| 12 | External Correspondence Service | external actor (dependee only) |
| 13 | External Clinical Services (treatment, laboratory, imaging) | external actor (dependee only) |
| 14 | External Payment Service Provider | external actor (dependee only) |
| 15 | Funding Organisation / Insurer | external actor (dependee only) |

## 5. 数据包：SD 的 40 条依赖

| 类型 | Depender | Dependee | Dependum（依赖的东西） |
| --- | --- | --- | --- |
| Goal | Patient / Authorised Representative | Consultant / Clinical Team | Receive clinically appropriate treatment |
| Goal | Finance Team | Treatment & Chemotherapy Bookings Team | Funding confirmed before treatment |
| Soft goal | Patient / Authorised Representative | Finance Team | Protect personal and financial information |
| Soft goal | Consultant / Clinical Team | Medical Secretaries | Administrative burden minimised |
| Soft goal | Patient Pathway Coordinators | Hospital Management Team | Pathway delays visible and escalated |
| Task | Patient / Authorised Representative | Outpatient Bookings Team | Offer a timely new patient appointment |
| Task | Patient / Authorised Representative | Clinical Nurse Specialist Team | Provide clinical advice and support |
| Task | Consultant / Clinical Team | Medical Secretaries | Administer and distribute clinic letters |
| Task | Finance Team | Outpatient Bookings Team | Refer paid appointment changes |
| Task | Call Handling Team | Clinical Nurse Specialist Team | Answer clinical enquiries |
| Task | Call Handling Team | Finance Team | Answer payment and funding enquiries |
| Task | Patient / Authorised Representative | Call Handling Team | Classify and route the enquiry |
| Task | Patient Pathway Coordinators | Consultant / Clinical Team | Complete and approve clinic letters |
| Task | Outpatient Bookings Team | External Correspondence Service | Send appointment confirmation letters |
| Task | Finance Team | External Payment Service Provider | Process payment and return the status |
| Task | Medical Secretaries | External Correspondence Service | Distribute clinic letters |
| Task | Medical Secretaries | Referring Organisation (GP or other hospital) | Supply missing referral information |
| Task | Outpatient Bookings Team | Patient / Authorised Representative | Confirm attendance by telephone |
| Task | Patient Pathway Coordinators | Referring Organisation (GP or other hospital) | Inform the referring organisation of pathway changes |
| Resource | Referring Organisation (GP or other hospital) | Medical Secretaries | Complete referral documentation |
| Resource | Referring Organisation (GP or other hospital) | Consultant / Clinical Team | Referral decision and recorded reason |
| Resource | Medical Secretaries | Consultant / Clinical Team | Referral checked and prepared for review |
| Resource | Medical Secretaries | Patient / Authorised Representative | Accurate patient identification |
| Resource | Consultant / Clinical Team | Outpatient Bookings Team | Accepted referral with priority and timeframe |
| Resource | Consultant / Clinical Team | Treatment & Chemotherapy Bookings Team | Authorised Treatment Booking Request |
| Resource | Consultant / Clinical Team | Finance Team | Clinical authorisation for urgent treatment |
| Resource | Consultant / Clinical Team | Clinical Nurse Specialist Team | Updated treatment plan |
| Resource | Consultant / Clinical Team | Patient / Authorised Representative | Informed consent to treatment |
| Resource | Outpatient Bookings Team | Consultant / Clinical Team | Confirmed appointment and contact outcome |
| Resource | Treatment & Chemotherapy Bookings Team | Finance Team | Treatment charge and schedule details |
| Resource | Treatment & Chemotherapy Bookings Team | Consultant / Clinical Team | Confirmed treatment schedule |
| Resource | Patient Pathway Coordinators | Patient / Authorised Representative | Accessible communication preferences |
| Resource | Hospital Management Team | Patient Pathway Coordinators | Outstanding correspondence report |
| Resource | Hospital Management Team | Finance Team | Funding, payment and refund reports |
| Resource | Hospital Management Team | Outpatient Bookings Team | Waiting time and contact attempt reports |
| Resource | Outpatient Bookings Team | External Scheduling Service | Available appointment slots |
| Resource | Consultant / Clinical Team | External Clinical Services (treatment, laboratory, imaging) | Investigation and test results |
| Resource | Treatment & Chemotherapy Bookings Team | External Clinical Services (treatment, laboratory, imaging) | Treatment, laboratory and imaging capacity |
| Resource | Finance Team | Funding Organisation / Insurer | Funding authorisation, amount and limitations |
| Resource | Clinical Nurse Specialist Team | External Clinical Services (treatment, laboratory, imaging) | Blood test and assessment results |

## 6. 数据包：SR 打开的 7 个 actor

| Actor id | 名称 | 元素数 | 构成 |
| --- | --- | --- | --- |
| `ACT_Consultant` | Consultant / Clinical Team | 10 | 3 goal, 1 soft goal, 6 task |
| `ACT_Treatment` | Treatment & Chemotherapy Bookings Team | 9 | 3 goal, 2 soft goal, 4 task |
| `ACT_Secretary` | Medical Secretaries | 8 | 2 goal, 2 soft goal, 4 task |
| `ACT_Finance` | Finance Team | 10 | 3 goal, 2 soft goal, 5 task |
| `ACT_Bookings` | Outpatient Bookings Team | 9 | 2 goal, 2 soft goal, 5 task |
| `ACT_Pathway` | Patient Pathway Coordinators | 8 | 2 goal, 2 soft goal, 4 task |
| `ACT_CNS` | Clinical Nurse Specialist Team | 7 | 2 goal, 1 soft goal, 4 task |

## 7. 数据包：SR 的 61 个 intentional element

`col` / `row` 是生成器的网格坐标（3 列 × 4 行），照着摆就不用重新排版。

| Actor | 元素 id | 类型 | 名称 | col | row |
| --- | --- | --- | --- | --- | --- |
| Consultant / Clinical Team | `T_C0` | Task | Manage the patient clinical pathway | 0 | 0 |
| Consultant / Clinical Team | `G_C1` | Goal | Referral decision justified and recorded | 0 | 1 |
| Consultant / Clinical Team | `G_C2` | Goal | Treatment authorised and auditable | 1 | 1 |
| Consultant / Clinical Team | `G_C3` | Goal | Correspondence clinically accurate | 2 | 1 |
| Consultant / Clinical Team | `T_C1` | Task | Perform clinical review of the referral | 0 | 2 |
| Consultant / Clinical Team | `T_C2` | Task | Record decision, rationale and clinician | 1 | 2 |
| Consultant / Clinical Team | `T_C3` | Task | Obtain and record patient consent | 2 | 2 |
| Consultant / Clinical Team | `T_C4` | Task | Create and authorise Treatment Booking Request | 0 | 3 |
| Consultant / Clinical Team | `T_C5` | Task | Approve clinic letter content | 1 | 3 |
| Consultant / Clinical Team | `S_C1` | Soft goal | Clinical accountability maintained | 2 | 3 |
| Treatment & Chemotherapy Bookings Team | `T_T0` | Task | Coordinate and confirm treatment appointments | 0 | 0 |
| Treatment & Chemotherapy Bookings Team | `G_T1` | Goal | Treatment scheduled without duplication | 0 | 1 |
| Treatment & Chemotherapy Bookings Team | `G_T2` | Goal | Only authorised requests processed | 1 | 1 |
| Treatment & Chemotherapy Bookings Team | `G_T3` | Goal | External capacity used safely | 2 | 1 |
| Treatment & Chemotherapy Bookings Team | `T_T1` | Task | Validate the authorised request | 0 | 2 |
| Treatment & Chemotherapy Bookings Team | `T_T2` | Task | Request treatment appointments from external services | 1 | 2 |
| Treatment & Chemotherapy Bookings Team | `T_T3` | Task | Keep the booking pending and record the retry | 2 | 2 |
| Treatment & Chemotherapy Bookings Team | `S_T1` | Soft goal | No duplicate appointments created | 0 | 3 |
| Treatment & Chemotherapy Bookings Team | `S_T2` | Soft goal | Treatment delays visible to the team | 1 | 3 |
| Medical Secretaries | `T_S0` | Task | Process incoming referrals and correspondence | 0 | 0 |
| Medical Secretaries | `G_S1` | Goal | Referral prepared for clinical review | 0 | 1 |
| Medical Secretaries | `G_S2` | Goal | Clinic letter processed without changing clinical meaning | 1 | 1 |
| Medical Secretaries | `T_S1` | Task | Check referral documentation completeness | 0 | 2 |
| Medical Secretaries | `T_S2` | Task | Request missing documentation | 1 | 2 |
| Medical Secretaries | `T_S3` | Task | Perform administrative checks and confirm recipients | 2 | 2 |
| Medical Secretaries | `S_S1` | Soft goal | No clinical judgement by administrative staff | 2 | 1 |
| Medical Secretaries | `S_S2` | Soft goal | Referral administration kept proportionate | 0 | 3 |
| Finance Team | `T_F0` | Task | Administer funding, payment and refunds | 0 | 0 |
| Finance Team | `G_F1` | Goal | Funding route determined and recorded | 0 | 1 |
| Finance Team | `G_F2` | Goal | Payment collected without double charging | 1 | 1 |
| Finance Team | `G_F3` | Goal | Refunds decided under financial authority | 2 | 1 |
| Finance Team | `T_F1` | Task | Request funding approval or additional payment | 0 | 2 |
| Finance Team | `T_F2` | Task | Send the secure payment request | 1 | 2 |
| Finance Team | `T_F3` | Task | Mark unexplained transactions for investigation | 2 | 2 |
| Finance Team | `T_F4` | Task | Determine retention, transfer or refund | 0 | 3 |
| Finance Team | `S_F1` | Soft goal | Patient is never charged twice | 1 | 3 |
| Finance Team | `S_F2` | Soft goal | No unnecessary financial data stored | 2 | 3 |
| Outpatient Bookings Team | `T_B0` | Task | Book and confirm new patient appointments | 0 | 0 |
| Outpatient Bookings Team | `G_B1` | Goal | Appointment offered within the requested period | 0 | 1 |
| Outpatient Bookings Team | `G_B2` | Goal | Patient informed and attendance confirmed | 1 | 1 |
| Outpatient Bookings Team | `T_B1` | Task | Validate the booking request and its urgency | 0 | 2 |
| Outpatient Bookings Team | `T_B2` | Task | Query the external scheduling service | 1 | 2 |
| Outpatient Bookings Team | `T_B3` | Task | Book and confirm the appointment in HPAS | 2 | 2 |
| Outpatient Bookings Team | `T_B4` | Task | Telephone the patient when within 14 days | 0 | 3 |
| Outpatient Bookings Team | `S_B1` | Soft goal | Never booked silently outside the clinical period | 2 | 1 |
| Outpatient Bookings Team | `S_B2` | Soft goal | No duplicate appointments | 1 | 3 |
| Patient Pathway Coordinators | `T_P0` | Task | Monitor and unblock patient pathways | 0 | 0 |
| Patient Pathway Coordinators | `G_P1` | Goal | Pathways progress within the clinical timescale | 0 | 1 |
| Patient Pathway Coordinators | `G_P2` | Goal | Outstanding correspondence escalated | 1 | 1 |
| Patient Pathway Coordinators | `T_P1` | Task | Resolve capacity when no suitable slot exists | 0 | 2 |
| Patient Pathway Coordinators | `T_P2` | Task | Issue weekly reminders for outstanding letters | 1 | 2 |
| Patient Pathway Coordinators | `T_P3` | Task | Escalate after one month and after three months | 2 | 2 |
| Patient Pathway Coordinators | `S_P1` | Soft goal | Delays visible before they become harm | 2 | 1 |
| Patient Pathway Coordinators | `S_P2` | Soft goal | Escalation proportionate, not repetitive | 0 | 3 |
| Clinical Nurse Specialist Team | `T_N0` | Task | Provide clinical advice and support | 0 | 0 |
| Clinical Nurse Specialist Team | `G_N1` | Goal | Patients receive clinically safe advice | 0 | 1 |
| Clinical Nurse Specialist Team | `G_N2` | Goal | Clinical enquiries handled by qualified staff | 1 | 1 |
| Clinical Nurse Specialist Team | `T_N1` | Task | Advise when a patient declines treatment | 0 | 2 |
| Clinical Nurse Specialist Team | `T_N2` | Task | Answer clinical enquiries referred by call handlers | 1 | 2 |
| Clinical Nurse Specialist Team | `T_N3` | Task | Handle urgent clinical concerns | 2 | 2 |
| Clinical Nurse Specialist Team | `S_N1` | Soft goal | No clinical advice from non-clinical staff | 2 | 1 |

## 8. 数据包：SR 的 9 条 boundary dependency

| 来源 actor | 来源元素 | 指向 | 类型 | Dependum |
| --- | --- | --- | --- | --- |
| ACT_Consultant | `T_C1` | A_Patient | Goal | Receive clinically appropriate treatment |
| ACT_Consultant | `T_C4` | A_Clinical | Resource | Investigation and test results |
| ACT_Secretary | `T_S3` | A_Correspondence | Task | Distribute clinic letters |
| ACT_Secretary | `T_S2` | A_Referrer | Task | Supply missing referral information |
| ACT_Finance | `T_F2` | A_PSP | Task | Process payment and return the status |
| ACT_Bookings | `T_B2` | A_Scheduling | Resource | Available appointment slots |
| ACT_Pathway | `T_P2` | A_Referrer | Task | Inform the referring organisation of pathway changes |
| ACT_Bookings | `T_B4` | A_Patient | Task | Confirm attendance by telephone |
| ACT_CNS | `T_N3` | A_Clinical | Resource | Blood test and assessment results |

---

## 9. 必须修的一致性缺口（**评审最容易抓这里**）

作品集 Task 02 的 B.5 写着：

> The SR was checked against the SD... each boundary link was matched to a dependency drawn in the SD.
> The check found one inconsistency on the first pass... which was corrected.

`istar-assumptions.md` 的 IA-09 也写着 `Every dependency drawn in the SR also appears in the SD model`。

**但把 SR 的每一条 boundary dependency 拿去 SD 里逐条比对，结果是：**

- 完全一致：**9 / 9**
- 指向同一对 actor、但名字或类型不同：**0**
- SD 里根本没有这条依赖：**0**

| SR 的来源 actor | 指向 | 类型 | Dependum | 与 SD 的比对 |
| --- | --- | --- | --- | --- |
| Consultant / Clinical Team | Patient / Authorised Representative | Goal | Receive clinically appropriate treatment | 一致（SR 里方向相反，符合 i\* 记法） |
| Consultant / Clinical Team | External Clinical Services (treatment, laboratory, imaging) | Resource | Investigation and test results | 一致 |
| Medical Secretaries | External Correspondence Service | Task | Distribute clinic letters | 一致 |
| Medical Secretaries | Referring Organisation (GP or other hospital) | Task | Supply missing referral information | 一致 |
| Finance Team | External Payment Service Provider | Task | Process payment and return the status | 一致 |
| Outpatient Bookings Team | External Scheduling Service | Resource | Available appointment slots | 一致 |
| Patient Pathway Coordinators | Referring Organisation (GP or other hospital) | Task | Inform the referring organisation of pathway changes | 一致 |
| Outpatient Bookings Team | Patient / Authorised Representative | Task | Confirm attendance by telephone | 一致 |
| Clinical Nurse Specialist Team | External Clinical Services (treatment, laboratory, imaging) | Resource | Blood test and assessment results | 一致 |

**必须做的选择（二选一，然后统一）：**

**方案 A（推荐，改动小）：把 SR 的边界依赖改成和 SD 完全一致。**
在 piStar 里把上面标了「名字/类型不同」的 dependum 文本改成 SD 里的名字；
标了「归属不同」的，改 `fromEl` 指向正确的元素。然后重新导出 SR 的 PDF。
这样 SD 的 37 条、SR 的 9 条都不用动，正文数字也不用改。

**方案 B：补 SD。** 如果认为某条依赖本来就该有（例如
`Patient Pathway Coordinators → Referring Organisation : Inform the referring organisation of pathway changes`），
就把它加进 SD。代价是 SD 变成 38 条以上，**作品集正文 B.2 的 `37 dependencies` 和 SD 图都要跟着改**。

> 另一处独立的小问题：SD 写 `GP or **other** hospital`，SR 写 `GP or **another** hospital`，统一成一个写法。

修完跑 `python 09_Tests_and_Tools/validate-istar.py`，
`boundaries matching an SD dependency` 那一行应该变成 9/9。

---

## 10. 重画之后的自检命令

```powershell
# 1) 源文件本身是否自洽（7 个 actor / 61 元素 / 9 边界，元素 id 唯一，边界引用有效）
python 09_Tests_and_Tools/validate-istar.py

# 2) 源文件与交付图是否一致（会重新从 SVG 读一遍元素清单比对）
python 09_Tests_and_Tools/rebuild-istar-source.py --check-only

# 3) 重新导出 piStar 工程
python 09_Tests_and_Tools/export-pistar-projects.py
```

---

## 11. 时间预算（给组员）

| 步骤 | 内容 | 预估 |
| --- | --- | --- |
| 1-3 | 导入两个工程、调布局 | 1 小时 |
| 4 | 补 SR 内部链接（分解 + means-end + 9 条贡献） | 2-3 小时 |
| 5 | 一致性检查 + 统一 actor 名字 | 30 分钟 |
| 6-7 | 导出 PDF/PNG/SVG，核对正文数字 | 1 小时 |
| | **合计** | **约半天** |

> 如果只是要交作业、不打算重画：**直接用仓库里现有的 PDF/SVG**，
> 只需要 (a) 把 SD/SR 里那个 `other` / `another` 统一，(b) 确认正文数字和图一致。这约 20 分钟。

