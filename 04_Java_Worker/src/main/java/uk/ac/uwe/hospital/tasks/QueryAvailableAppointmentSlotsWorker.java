package uk.ac.uwe.hospital.tasks;

import uk.ac.uwe.hospital.AbstractWorker;
import uk.ac.uwe.hospital.JobContext;
import uk.ac.uwe.hospital.support.ExternalServices;
import uk.ac.uwe.hospital.support.HospitalStore;
import uk.ac.uwe.hospital.support.Ids;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * {@code query-available-appointment-slots} - asks the hospital's external
 * scheduling service for an appointment that fits the request.
 *
 * <p>This worker owns {@code suitableSlotFound}, which the model's
 * {@code G_SlotsAvailable} gateway reads. Two distinct outcomes must not be
 * conflated:
 *
 * <ul>
 *   <li>the service answered and there is <b>no</b> slot - {@code suitableSlotFound = false},
 *       which routes to the Patient Pathway Coordinator, exactly as REQ-12 requires;</li>
 *   <li>the service did <b>not answer</b> - the job is failed so the engine retries it,
 *       because "no capacity" and "no answer" are different facts and reporting the
 *       second as the first would send a patient down an escalation path for a
 *       network fault.</li>
 * </ul>
 *
 * <p>中文：本类服务于 BPMN 服务任务 T_QueryAvailableSlots（向外部排班服务查询可预约号源），
 * 作业类型为 {@code query-available-appointment-slots}。号源由外部排班服务掌握，医院系统
 * 无法自行创造容量，所以本工人只做"查询并如实转述"：查到号就写 suitableSlotFound = true，
 * 让网关 G_SlotsAvailable 走向 T_SelectAndBookSlot（在顾问给定的时间窗内安排预约）；
 * 查不到号就写 suitableSlotFound = false，把病例转交患者路径协调员处理容量约束。
 * 两种"没有号"必须严格区分，也就是上面英文说明的重点：服务明确答复"没有"是业务事实，
 * 服务根本没有答复则是可以重试的技术故障，把它当成前者会把患者送上错误的升级路径。
 */
public class QueryAvailableAppointmentSlotsWorker extends AbstractWorker {

    /** 中文：作业类型标识，必须与模型中 zeebe:taskDefinition 的 type 逐字一致，否则引擎不会派发作业。 */
    public static final String JOB_TYPE = "query-available-appointment-slots";

    /** 中文：用"工人族名 + 作业类型"拼出订阅名，便于在 Zeebe 与日志中区分同一类型的多个工人实例。 */
    public QueryAvailableAppointmentSlotsWorker() {
        super("hospital-external-workers:" + JOB_TYPE);
    }

    /** 中文：返回本工人订阅的作业类型，基类据此注册 Zeebe 作业工人并接收该类型的作业。 */
    @Override
    public String jobType() {
        return JOB_TYPE;
    }

    /**
     * 中文：处理一次"查询可预约号源"作业。读取专科、紧急程度与期望时间窗，向外部排班服务查询，
     * 再把号源与 suitableSlotFound 写回流程：服务明确答复"无号"是业务结果，服务未应答则是
     * 可重试故障，两者绝不混同。
     */
    @Override
    protected void handle(JobContext ctx) {
        // 中文：patientId 是必填输入，缺失说明预约请求数据不完整，以校验异常终止本次作业。
        String patientId = ctx.requireString("patientId");
        // 中文：专科缺失时退化为中性描述，保证查询与日志仍可读，但不假装知道具体专科。
        String speciality = ctx.findString("requestedSpeciality").orElse("specialist service");
        // 中文：紧急程度默认按"常规"处理：只有明确写了 urgent 才走加急窗口，避免默认加急挤占急诊资源。
        String urgency = ctx.findString("referralUrgency").orElse("routine");
        // 中文：期望时间窗以天数为准；没有该变量时，用旧的"14 天内"布尔标志换算成 14 天，
        // 中文：两者都没有才放宽到 28 天。默认值的用意是宁可检索更宽的窗口，也不要因表单缺项而查不到号。
        int withinDays = ctx.intOr("preferredTimeframeDays", ctx.bool("appointmentWithin14Days", false) ? 14 : 28);
        // 中文：urgent 只做一次大小写无关的比较，供外部服务决定检索窗口与号源优先级。
        boolean urgent = "urgent".equalsIgnoreCase(urgency);

        // 中文：这是真正的跨系统调用。排班服务不可用时会在内部抛 TransientJobException，
        // 中文：即"服务没有答复"：作业应失败并交给引擎重试，绝不在这里伪造一个"没有号"的结论。
        ExternalServices.Scheduling.Result result =
                ExternalServices.Scheduling.findSlots(speciality, withinDays, urgent);

        // 中文：把外部服务返回的号源逐条摊平成 Map。显式转换是为了固定写回流程的变量结构，
        // 中文：不直接把内部 record 序列化进流程变量，从而让流程变量契约保持稳定可控。
        List<Map<String, Object>> slots = new ArrayList<>();
        for (ExternalServices.Slot s : result.slots()) {
            slots.add(Map.of("reference", s.reference(), "date", s.date().toString(),
                    "clinic", s.clinic(), "consultant", s.consultant()));
        }

        // 中文：episodeId 缺失时按患者号推导；等外部结果到手后再补全就诊关联信息，避免无谓的编号生成。
        String episodeId = ctx.findString("episodeId").orElseGet(() -> Ids.episode(patientId));
        // 中文：found 就是本工人拥有的 suitableSlotFound：网关 G_SlotsAvailable 依它分流——
        // 中文：为真则进入选号与预约的人工任务，为假则转交患者路径协调员处理容量约束（REQ-12）。
        boolean found = !result.slots().isEmpty();

        // 中文：用 LinkedHashMap 保证变量写回顺序稳定，便于在 Operate 与日志中阅读同一次查询的结果。
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("episodeId", episodeId);
        // 中文：即便"没有号"也必须显式写回 suitableSlotFound = false，
        // 中文：否则网关表达式取不到值，流程会走到错误的分支上。
        out.put("suitableSlotFound", found);
        // 中文：schedulingServiceAnswered 记录服务到底有没有答复，用于把"问了但没有"与
        // 中文："根本没问着"区分开，供运维排查网络问题，而不是当作容量结论使用。
        out.put("schedulingServiceAnswered", result.available());
        // 中文：号源总数与明细一起写回，供人工选号时直接查看，无需再次调用外部服务。
        out.put("availableSlotCount", slots.size());
        out.put("availableSlots", slots);
        // 中文：回写实际用于检索的专科，便于人工核对"查的是不是这个专科"。
        out.put("requestedSpeciality", speciality);
        // 中文：记录查询时间，是判断号源信息是否过期的依据。
        out.put("schedulingQueriedAt", Instant.now().toString());
        // 中文：只有确实查到号时才写预约凭证与最早日期：没有号源却留下凭证，
        // 中文：会让下游误以为已有可预约的号，属于可能引发重复预约的数据污染。
        if (found) {
            out.put("schedulingReference", Ids.scheduling());
            // 中文：取第 0 条基于外部服务按日期升序返回的约定，作为最早可约日期供人工优先安排。
            out.put("earliestSlotDate", result.slots().get(0).date().toString());
        }
        // 中文：setAll 一次性把上述变量写回流程，供网关与后续人工任务使用。
        ctx.setAll(out);

        // 中文：note 只是给运维与审计看的说明文本，用两种措辞区分"查到号"和"服务答复无号"，
        // 中文：它不参与任何分支判断，因此措辞的改动不会影响流程行为。
        ctx.note(found
                ? "scheduling service returned " + slots.size() + " slot(s)"
                : "scheduling service answered with no suitable slot inside " + withinDays + " day(s)");

        // 中文：按 episodeId 归集每次检索，键用当前毫秒时间戳，使多次查询互不覆盖，
        // 中文：为容量约束的处理过程保留可回看的历史，而不是只留下最后一次。
        HospitalStore.get().put(episodeId, "slotSearches", String.valueOf(Instant.now().toEpochMilli()),
                Map.of("speciality", speciality, "urgency", urgency, "withinDays", withinDays,
                        "found", found, "count", slots.size()));
    }
}
