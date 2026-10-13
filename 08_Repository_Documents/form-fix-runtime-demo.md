# 运行演示：字段类型改完之后，跑起来到底看到什么

> 配套文件：`08_Repository_Documents/form-field-change-log.md`（改了什么）、
> `08_Repository_Documents/form-field-fix-briefing.md`（汇报稿）。
> 本文回答的是另一个问题：**这些改动在运行时怎么被看见、怎么被证明。**

---

## 0. 先把层次说清楚（这是最容易被追问的地方）

表单是 **Tasklist 的渲染层和提交层**：它决定"人能看到什么控件、能提交什么值"。
它**不决定引擎怎么跑**：引擎只认流程变量。

由此得到一条必须主动说出来的结论：

> **只改表单，`run-worker-demo.mjs` 和 `run-acceptance.mjs` 的结果不会有任何变化。**

因为这两个脚本是通过 Zeebe API 直接写流程变量的，**既不会渲染表单，也不会跑表单校验**。
证据就在交付证据里：`accessibleFormatRequired` 在
`05_Test_Evidence/worker-run/worker-demo-2026-09-28T12-13-00-853Z.json:94` 里是脚本直接设成
`"false"` 的，不是人在界面上填的。

所以如果评审说"你重跑一遍验收给我看"，那是**看不到差别**的——这不是改动没生效，而是工具用错了。

### 那到底在哪三处能看见差别

| # | 位置 | 改前 | 改后 | 怎么取证 | 对 API 路径也成立吗 |
| --- | --- | --- | --- | --- | --- |
| 1 | **Tasklist 控件外观** | 全部是文本框/复选框 | 出现日期选择器、数字框、下拉框、多行文本 | 截图（见第 4 节） | 不适用（API 不渲染表单） |
| 2 | **Tasklist 提交行为** | 空着也能提交 | 必填/格式不合规**提交被拦** | 截图或录屏 | 不适用 |
| 3 | **Operate 里的流程路径** | 见下方"谁提供值"三种情况 | 见下方 | 实例的"已到达元素"对比 | **只在人提供值这一种情况下成立** |

> **重要限定：第 3 行不是无条件成立的。** 它描述的是"人通过 Tasklist 提供变量"这条路径。
> 在 API 路径上没有任何区别——因为本次改动没有动流程变量契约。这不是缺点，正是安全性的证明；
> 但如果汇报时把它说成"流程路径被修正了"，会被当场问倒。下面把三种情况分开讲。

### 第 3 行到底谁有区别：按"谁提供值"分三种

| 谁提供值 | 具体例子 | 改前 | 改后 | 有区别吗 | 证据 |
| --- | --- | --- | --- | --- | --- |
| **A. API 脚本直接写**（现有验收证据走的就是这条） | 证据里 `referralDecision` 写的是 `"accepted"`、`enquiryType` 写的是 `"administrative"`、`paymentStatus` 写的是 `"confirmed"`，全部是模型认识的字面量 | 网关走**正确**分支 | 不变 | **没有区别** | 交付证据里 `referralDecision`/`referralUrgency` 各 108 次、`paymentStatus` 18 次、`enquiryType` 12 次，取值全部正确 |
| **B. 人在 Tasklist 里填**（本次改动影响的范围） | 同样的字段，改前是自由文本框，人照着标签打 `Accept` / `Administrative` / `Confirmed`；改后是下拉框，只能选 | 没有条件成立 → **落默认分支**（如 `Accept` 被判成 Rejected） | 条件成立 → **正确分支** | **有区别** | `demo-form-control-impact.py` 算出的 10 个走向改变 |
| **C. 变量根本没被设过** | `letterDelayDays`、`letterAgeMonths`、`accepted` | FEEL 取 null → **落默认分支** | 人现在能填了 → 正确分支（`accepted` 除外，见 DEF-FORM-06） | **有区别，而且 API 路径也一样** | 见下 |

**C 这一类才是真正在两条路径上都存在的缺陷**，而且恰恰是**证据从未覆盖过的地方**：

| 元素 | 在全部交付证据里出现的次数 |
| --- | --- |
| `G_LetterOnTime`、`G_LetterAge`、`G_LetterAgeExtended` | **0** |
| `T_Escalate`、`T_WeeklyReminder`、`T_EscalateToManager`、`T_EscalateToHigherManagement`、`T_ReminderInterval` | **0** |

也就是说：**S1/S3 的延迟信函升级链，你们的验收和 demo 一次都没有走到过。**
所以那个"复选框 + 数值比较"的 bug 从来没被触发，也就从来没人发现。
`accepted` 同样从未被赋过值，所以 `G_Accepted` 无论走哪条路都只能落默认分支——那是模型缺陷（DEF-FORM-06），本次没修。


---

## 1. 最有说服力的一处：延迟信函的升级链

这是本次发现的真 bug。`letterDelayDays` 和 `letterAgeMonths` 原本是复选框，
但模型里拿它们做**数值比较**：

- `02_BPMN_Models/S1_Strategic_Landscape.bpmn:230,233` — `letterDelayDays <= 7` / `> 7`
- `02_BPMN_Models/S3_Strategic_Treatment_To_Aftercare.bpmn:584,589,594,599` — `letterAgeMonths < 1` / `< 3` / `>= 1` / `>= 3`

复选框只能产出 `true`/`false`。在 FEEL 里，布尔值和数字比大小**求值为 null**，
Zeebe 把 null 条件当作**不成立**，于是网关落到 `default` 分支上。

而这两个网关的 default 恰好是"坏的那一支"：

| 网关 | 它的默认分支 | 后果 |
| --- | --- | --- |
| `G_LetterOnTime` | `F_22` = "Delayed" → 升级延迟信函 | **每一封信都被判定为超期** |
| `G_LetterAge` | `F_F9` = "Less than one month" → 等一周 | **永远回到每周提醒循环，永远升级不到行政管理员** |
| `G_LetterAgeExtended` | `F_F11` = "Less than three months" → 发每周提醒 | **永远升级不到高层管理** |

也就是说：改之前，一个真实的人在 Tasklist 里操作，**这封超期信函的升级链是断的**——
系统会一周一周地重复提醒，永远不升级。改之后填天数/月数，链路才通。

改后正确行为（同一批条件、同一批 default）：

| 人填的值 | 网关判定 | 走到哪 |
| --- | --- | --- |
| `letterDelayDays = 3` | `3 <= 7` 成立 | "Within seven days" → 处理患者咨询 |
| `letterAgeMonths = 2` | `>= 1` 成立 | "More than one month" → **升级到行政管理员** |
| `letterAgeMonths = 4` | `>= 3` 成立 | "More than three months" → **升级到高层管理** |

---

## 2. 全部对照：12 个网关判定，10 个走向改变

下面这张表不是手写的，是 `09_Tests_and_Tools/demo-form-control-impact.py` **直接读模型的
条件表达式和 `default` 属性算出来的**。它把每个网关算两遍：一遍喂"旧控件会产出的值"
（复选框给 `true`，文本框给人打进去的字），一遍喂"新控件会产出的值"。

```powershell
python 09_Tests_and_Tools/demo-form-control-impact.py --markdown out.md
```

| Model | Gateway | Variable | Before the fix | After the fix | Verdict |
| --- | --- | --- | --- | --- | --- |
| `S1_Strategic_Landscape` | `G_LetterOnTime` | `letterDelayDays` | `True` → Delayed → 升级延迟信函<br>*没有条件成立，落到默认分支* | `3` → Within seven days → 处理患者咨询<br>*条件成立* | **DIFFERENT PATH** |
| `S3_...Aftercare` | `G_LetterAge` | `letterAgeMonths` | `True` → Less than one month → 等一周<br>*落到默认分支* | `2` → More than one month → **升级到行政管理员**<br>*条件成立* | **DIFFERENT PATH** |
| `S3_...Aftercare` | `G_LetterAgeExtended` | `letterAgeMonths` | `True` → Less than three months → 发每周提醒<br>*落到默认分支* | `2` → Less than three months → 发每周提醒<br>*条件成立* | 目标相同，但改前是"撞"上默认分支 |
| `S3_...Aftercare` | `G_LetterAge` | `letterAgeMonths` | `True` → Less than one month → 等一周<br>*落到默认分支* | `4` → More than one month → **升级到行政管理员**<br>*条件成立* | **DIFFERENT PATH** |
| `S3_...Aftercare` | `G_LetterAgeExtended` | `letterAgeMonths` | `True` → Less than three months → 发每周提醒<br>*落到默认分支* | `4` → More than three months → **升级到高层管理**<br>*条件成立* | **DIFFERENT PATH** |
| `O1_Operational_Merged` | `G_ReferralDecision` | `referralDecision` | `'Accept'` → **Rejected** → 通知转诊结果<br>*落到默认分支* | `'accepted'` → **Accepted** → 转给门诊预约组<br>*条件成立* | **DIFFERENT PATH** |
| `S2_...Referral_To_Authorisation` | `G_ReferralDecision` | `referralDecision` | `'Accept'` → **Rejected** → 通知转诊结果<br>*落到默认分支* | `'accepted'` → **Accepted** → 转给门诊预约组<br>*条件成立* | **DIFFERENT PATH** |
| `S3_...Aftercare` | `G_EnquiryType` | `enquiryType` | `'Administrative'` → **Clinical** → 转临床护士<br>*落到默认分支* | `'administrative'` → **Administrative** → 转行政组<br>*条件成立* | **DIFFERENT PATH** |
| `O1_Operational_Merged` | `G_UrgentReferral` | `referralUrgency` | `'Urgent'` → Urgent → 加急预约<br>*落到默认分支* | `'urgent'` → Urgent → 加急预约<br>*条件成立* | 目标相同，但改前是"撞"上默认分支 |
| `S2_...Referral_To_Authorisation` | `G_UrgentReferral` | `referralUrgency` | `'Urgent'` → **Routine** → 正常查号<br>*落到默认分支* | `'urgent'` → **Urgent** → 加急预约<br>*条件成立* | **DIFFERENT PATH** |
| `O1_Operational_Merged` | `G_PaymentOutcome` | `paymentStatus` | `'Confirmed'` → **付款失败** → 让患者重试<br>*落到默认分支* | `'confirmed'` → **付款成功** → 记录付款<br>*条件成立* | **DIFFERENT PATH** |
| `S3_...Aftercare` | `G_PaymentOutcome` | `paymentStatus` | `'Confirmed'` → **付款失败** → 让患者重试<br>*落到默认分支* | `'confirmed'` → **付款成功** → 记录付款<br>*条件成立* | **DIFFERENT PATH** |

**12 个判定里 10 个走向改变。**

几个特别值得在汇报时点出来的：

- **`referralDecision`**：人在文本框里填 `Accept`（照着标签上的字抄），
  **转诊直接被判为"拒绝"**并通知转诊方；只有填对 `accepted` 才会转给预约组。
  这正好印证了你们缺陷日志里 DEF-09 记的"取值不一致"问题。
- **`enquiryType`**：填 `Administrative` 会被判成 **Clinical**，转给临床护士；
  而 `G_EnquiryType` 的默认分支就是 Clinical——**默认值偏向了临床**，所以填错会被静默升级。
  改成下拉框后，人只能选模型里认识的那几个值。
- **`paymentStatus`**：填 `Confirmed` 被判成 **付款失败**，让患者重试付款——这是财务事故级别的。
- 两处"目标相同但原因不同"（`G_UrgentReferral`@O1、`G_LetterAgeExtended`）说明：
  改前那个分支**只是碰巧和默认分支一致**，属于侥幸走对，不是逻辑走对。

---

## 3. 为什么你们现有的验收证据不会变（要主动说明）

| | API 路径（现有验收脚本） | Tasklist 路径（本次改动影响的范围） |
| --- | --- | --- |
| 谁在用 | 系统自动化 | 真实的人 |
| 变量怎么进去 | 脚本直接调 Zeebe API 写 | 人在表单里填，表单提交后写 |
| 会渲染表单吗 | **不会** | 会 |
| 会跑表单校验吗 | **不会** | 会 |
| 本次改动是否影响它 | **不影响** | **影响** |

结论：**本次改动没有改动流程变量契约**（`key` 一个没改、`type` 与 `key` 的对应关系没改、
模型和工作器一行未动），所以 API 路径保持不变——这恰恰是这次改动**安全**的证据。
但要看效果，必须走 Tasklist。

> 我在上一轮汇报稿里把 `accessibleFormatRequired` 那个分支写成"不可达"，措辞不准，这里更正：
> 准确说法是**"在 Tasklist 里不可达"**——没有任何表单采集它，人没法填；
> 但它可以被 API 直接设进去，你们的 demo 脚本就是这么干的。
> 另外 `S1_Strategic_Landscape.bpmn` 用的 `accepted` 变量，
> **在全部交付证据里从未被设置过**，所以 `G_Accepted` 在两种路径下都只会走默认分支，
> 那一条是真正的模型缺陷（记为 DEF-FORM-06）。

---

## 4. Tasklist 复现步骤（评审要看效果时按这个走）

前置：Camunda 8.10 起来（用你们自己的 `09_Tests_and_Tools/deploy-all.mjs`），
然后部署模型和表单。

### 演示 A：控件外观变了（30 秒，最直观）

1. 启动一个实例，走到 **"Record the payment reference, amount and date against the patient account"**（`T_RecordPayment`）。
2. 打开任务表单。

| | 改前 | 改后 |
| --- | --- | --- |
| 字段数 | **1 个**（患者标识） | **5 个** |
| 金额 | 无处可填 | **数字输入框**，带上下箭头 |
| 付款日期 | 无处可填 | **日期选择器**（点开是日历） |
| 币种 | 无处可填 | **下拉框**（GBP / EUR / USD） |

### 演示 B：空值提交被拦住（1 分钟）

1. 打开同一个表单，**什么都不填**，直接点提交。
2. 改前：表单提交成功（因为只有患者标识，而它是脚本设好的），流程继续往下走。
3. 改后：**提交被拒绝**，每个必填字段下方出现校验提示，流程不会前进。

### 演示 C：分支走向被修正（3 分钟，最有说服力）

以 `letterAgeMonths` 为例（`G_LetterAge`）：

1. 走到 **"Issue a weekly reminder to the responsible consultant"**（`T_WeeklyReminder`）。
2. 在表单里填月数：
   - 填 **2**（改前只能勾"是"，产出 `true`）
   - 改前结果：`true < 1` → null → 落到默认分支 → **回到"等一周"** → 实例在提醒循环里打转，Operate 里看不到 `T_EscalateToManager`
   - 改后结果：`2 >= 1` 成立 → **到 `T_EscalateToManager`（升级到行政管理员）**
3. 把实例的"已到达元素"列表截图对比：改前只看得到 `T_WeeklyReminder` 反复出现；
   改后能看得到 `G_LetterAge → T_EscalateToManager`。

### 演示 D：下拉框挡住了拼写错误（1 分钟）

1. 打开 **"Record the referral decision, rationale and responsible clinician"**（`T_RecordReferralDecision`）。
2. 改前：是自由文本框。填 `Accept` → 实例进入 **"Rejected"** 分支并通知转诊方。
3. 改后：是下拉框，**只能选** Accepted / Rejected / Information required / Redirected。
   选 "Accepted" 提交后，变量的字面量就是 `accepted`，实例进入 **"Accepted"** 分支。

---

## 5. 如果评审追问"你怎么证明这不是纸上功夫"

三句话：

1. **静态可核对**：`form-field-change-log.md` 是拿当前工作区和上一个提交版本对比**算**出来的，不是我写的说明；10 个类型纠错、41 个新增控件、115 个字段加校验，逐条可点开看。
2. **机器可判定**：三个项目自带校验器全部 clean；新增的 `validate-form-controls.py` 判定"25 个网关变量中 24 个已采集且必填、类型不匹配的控件 0 个"，退出码 0。
3. **语义可计算**：`demo-form-control-impact.py` 直接读模型条件和 `default` 算出 12 个网关判定，10 个走向改变——上表每一行都能用这个脚本重跑出来。

还没做、需要集群才能做的那一步是：**在 Tasklist 上按第 4 节走一遍并截图**，
结果存到 `05_Test_Evidence/screenshots/`（那一目录已经有 `05_tasklist.png`，可以放同一批）。
这一步我做不了，因为当前机器上没有运行中的 Camunda 集群、也没有 Docker。
