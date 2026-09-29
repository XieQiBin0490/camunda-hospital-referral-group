package uk.ac.uwe.hospital.tasks;

import uk.ac.uwe.hospital.AbstractWorker;
import uk.ac.uwe.hospital.JobContext;
import uk.ac.uwe.hospital.support.ExternalServices;
import uk.ac.uwe.hospital.support.HospitalStore;
import uk.ac.uwe.hospital.support.Ids;

import java.time.Instant;
import java.time.LocalDate;
import java.util.Map;

/**
 * {@code request-treatment-capacity} - asks the external treatment, laboratory
 * and imaging services whether the requested course can be delivered.
 *
 * <p>This worker owns {@code treatmentCapacityConfirmed}, which the model reads
 * before it will confirm a schedule. It is the clearest case in the whole build
 * of a failure the process is expected to survive: REQ-16 says that when an
 * external service is temporarily unavailable the booking must <b>remain
 * pending</b>, the responsible team must be notified and further attempts must be
 * recorded <b>without creating duplicate appointments</b>. So an unavailable
 * resource is not an error and not a silent success - it is a first-class outcome
 * that leaves the instance on the pending branch with an incremented attempt
 * count and a next-attempt date.
 *
 * <p>A hard technical failure (the service not answering at all) is treated
 * differently again: the job is failed so the engine retries it, because a
 * network fault is not evidence about capacity.
 *
 * <p>中文：本类服务于 BPMN 服务任务 T_RequestTreatmentCapacity（向外部治疗、检验与影像服务
 * 申请治疗容量），作业类型为 {@code request-treatment-capacity}。它拥有
 * {@code treatmentCapacityConfirmed} 这一变量：网关 G_CapacityConfirmed 依据它决定流程是继续
 * 确认排期，还是进入"保持待定"的人工任务 T_KeepPending。REQ-16 要求外部服务临时不可用时
 * 预约必须保持待定、通知负责团队并记录后续尝试，且不得重复创建预约，所以"容量未确认"是一种
 * 正常的业务结果而不是错误：本工人写回尝试次数、下一次尝试日期与升级标志，让流程合法地停在
 * 待定分支上。只有服务完全没有应答这种硬故障才以可重试异常上交引擎，因为网络故障不能作为
 * 关于容量的证据。
 */
public class RequestTreatmentCapacityWorker extends AbstractWorker {

    /** 中文：作业类型标识，必须与模型中 zeebe:taskDefinition 的 type 逐字一致，否则引擎不会派发作业。 */
    public static final String JOB_TYPE = "request-treatment-capacity";

    /**
     * After this many failed attempts the case study wants an escalation, not another retry.
     *
     * <p>中文：尝试次数上限（含本次）。达到 3 次仍未确认容量时把 capacityEscalationRequired
     * 置真，流程应转人工升级而不是继续等待重试——这是案例研究对"反复申请仍无容量"的处置要求。
     */
    private static final int ATTEMPT_CAP = 3;

    /** 中文：用"工人族名 + 作业类型"拼出订阅名，便于在 Zeebe 与日志中区分同一类型的多个工人实例。 */
    public RequestTreatmentCapacityWorker() {
        super("hospital-external-workers:" + JOB_TYPE);
    }

    /** 中文：返回本工人订阅的作业类型，基类据此注册 Zeebe 作业工人并接收该类型的作业。 */
    @Override
    public String jobType() {
        return JOB_TYPE;
    }

    /**
     * 中文：处理一次"申请治疗容量"作业。先累加本次尝试序号，再向外部服务申请容量，然后按答复分两路
     * 写回：确认则记录容量凭证；未确认则保持预约待定，并写入尝试次数、下次尝试日期与升级标志
     * （REQ-16），全程不创建任何重复预约。
     */
    @Override
    protected void handle(JobContext ctx) {
        // 中文：patientId 是必填输入，缺失说明治疗申请数据不完整，以校验异常终止本次作业。
        String patientId = ctx.requireString("patientId");
        // 中文：治疗项目代码缺失时退化为中性描述，保证日志与容量记录仍可读，但不假装知道具体项目。
        String treatmentCode = ctx.findString("treatmentCode").orElse("unspecified treatment");
        // 中文：疗程次数默认 1：比起让外部服务收到 0，默认一次是最常见的业务情形，也更安全。
        int cycles = ctx.intOr("treatmentCycles", 1);
        // 中文：所需资源允许为空（例如不指定具体设备）；空值的含义是"没有特别要求"，不是"没有资源"。
        String resource = ctx.findString("requiredResource").orElse("");
        // 中文：episodeId 缺失时按患者号推导，保证容量申请与后续预约归集在同一次就诊之下。
        String episodeId = ctx.findString("episodeId").orElseGet(() -> Ids.episode(patientId));

        // 中文：尝试序号是 REQ-16 的核心：存储层按"作业类型 + 治疗项目"计数并自增，
        // 中文：既用来判断是否需要升级，也用来生成不会重复的预约键；同一 episode 再次进入仍可续算。
        int attempt = HospitalStore.get().nextAttempt(episodeId, JOB_TYPE + ":" + treatmentCode);

        // 中文：这是可配置的故障注入开关（系统属性优先，其次环境变量）。只在第 1 次尝试时生效，
        // 中文：这样演示能看到"先失败并保持待定、重试后成功"的完整路径，而不会永远失败下去。
        boolean forceUnavailable = attempt == 1
                && Boolean.parseBoolean(System.getProperty("hpas.capacity.unavailableOnce",
                        System.getenv().getOrDefault("HPAS_CAPACITY_UNAVAILABLEONCE", "false")));

        // 中文：注入时直接构造"服务明确答复无容量"的结果，模拟的是业务上的不可用答复（属于正常结果，
        // 中文：并带出不可用的资源名），而不是服务没有应答那种技术故障；后者由 request 内部抛可重试异常。
        ExternalServices.Capacity.Result result = forceUnavailable
                ? new ExternalServices.Capacity.Result(false, null, resource.isBlank() ? "external treatment service" : resource)
                : ExternalServices.Capacity.request(treatmentCode, cycles, resource);

        // 中文：在登记本次尝试之前先查该预约键是否已存在。键里带 attempt，因此同一次尝试被重复执行
        // 中文：时会被识别为"已有记录"，这正是 REQ-16 "记录后续尝试但不重复创建预约"的落地点。
        boolean duplicateGuarded = HospitalStore.get().existingAppointment(episodeId, treatmentCode + "#" + attempt).isEmpty();
        // 中文：indexAppointment 采用 putIfAbsent 语义，重复登记不会覆盖既有预约号，防止并发下重复预约。
        HospitalStore.get().indexAppointment(episodeId, treatmentCode + "#" + attempt, "CAP-" + attempt);

        // 中文：写回流程变量。treatmentCapacityConfirmed 由本工人拥有，网关 G_CapacityConfirmed
        // 中文：据此决定是继续确认排期还是进入"保持待定"的 T_KeepPending；
        // 中文：capacityAttemptCount 与时间戳用于统计重试次数，duplicateAppointmentCreated 恒为假，
        // 中文：因为预约本身由人工任务创建，本工人只做容量核查与尝试登记。
        ctx.set("episodeId", episodeId)
           .set("treatmentCapacityConfirmed", result.confirmed())
           .set("capacityAttemptCount", attempt)
           .set("capacityLastAttemptAt", Instant.now().toString())
           .set("duplicateAppointmentCreated", false)
           .note(result.confirmed()
                   ? "capacity confirmed on attempt " + attempt + " as " + result.reference()
                   : "no capacity on attempt " + attempt + " (" + result.unavailableResource() + "), booking stays pending");

        // 中文：容量确认分支：记录容量凭证、获批疗程数与实际使用的资源，
        // 中文：供后续排期、付款与病历归档环节引用，证明这份容量确实来自外部服务。
        if (result.confirmed()) {
            ctx.set("capacityReference", result.reference())
               .set("capacityConfirmedForCycles", cycles)
               .set("capacityConfirmedResource", resource.isBlank() ? "hospital facility" : resource);
            // 中文：把获批容量归入该 episode 的 capacity 集合（键为凭证号），
            // 中文：这是容量确实确认过的持久证据，也便于统计各资源的占用情况。
            HospitalStore.get().put(episodeId, "capacity", result.reference(), Map.of(
                    "reference", result.reference(), "treatmentCode", treatmentCode,
                    "cycles", cycles, "attempts", attempt, "confirmedAt", Instant.now().toString()));
        } else {
            // 中文：未确认分支不是错误，而是 REQ-16 要求的"保持待定"：记录不可用资源、待定起始时间、
            // 中文：下一次尝试日期、是否达到升级阈值以及此前的失败次数（attempt - 1），
            // 中文：让流程合法地停在此分支，由责任团队继续跟进，而不是无限重试下去。
            ctx.set("unavailableResource", result.unavailableResource())
               .set("capacityPendingSince", Instant.now().toString())
               .set("capacityNextAttemptDate", LocalDate.now().plusDays(1).toString())
               .set("capacityEscalationRequired", attempt >= ATTEMPT_CAP)
               .set("capacityRetryCount", attempt - 1);
            // 中文：命中已有记录时补一条说明，让运维明确知道本次只登记了重试，没有新增预约。
            if (duplicateGuarded) {
                ctx.note("retry recorded against the existing request; no duplicate appointment created");
            }
        }
    }
}
