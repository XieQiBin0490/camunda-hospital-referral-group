package uk.ac.uwe.hospital.tasks;

import uk.ac.uwe.hospital.AbstractWorker;
import uk.ac.uwe.hospital.JobContext;
import uk.ac.uwe.hospital.support.HospitalStore;
import uk.ac.uwe.hospital.support.Ids;

import java.time.Instant;
import java.util.Map;

/**
 * {@code referring-org-submit-patient-referral} - the referring organisation
 * composes the referral it is about to send.
 *
 * <p>This worker belongs to the <em>referring organisation's</em> pool
 * ({@code PR_ReferringOrganisation}), not to the hospital. It is the first step
 * of the cross-pool exchange: the referral is prepared here, then handed to the
 * patient-referral message throw event, which publishes it and starts an
 * instance of the hospital process.
 *
 * <p>Its one output that matters downstream is {@code referralReference}. That
 * value travels to the hospital inside the message payload, the hospital echoes
 * it back on the outcome notification, and the referring pool's message catch
 * event correlates on it. If it is missing or unstable the round trip cannot
 * close, so it is generated once here and never regenerated.
 *
 * <p>中文：本工作器属于转诊机构自己的池 PR_ReferringOrganisation，而不是医院侧。它是整条
 * 跨池交互的第一步：在这里把转诊单准备好，再交给“患者转诊”消息抛出事件发布出去，
 * 由那条消息启动一个医院流程实例。
 *
 * <p>中文：真正影响下游的输出只有 referralReference 一个。它会随消息负载进入医院侧，
 * 医院在回传结论通知时再把它带回来，转诊池的消息捕获事件正是按它做关联。若该值缺失或
 * 每次重新生成，这个往返就闭合不了，所以它只在此处生成一次，后续任何环节都不再重算。
 */
public class SubmitPatientReferralWorker extends AbstractWorker {

    /** 中文：作业类型标识，必须与模型中 zeebe:taskDefinition 的 type 逐字一致，否则引擎不会派发作业。 */
    public static final String JOB_TYPE = "referring-org-submit-patient-referral";

    /** 中文：用"工人族名 + 作业类型"拼出订阅名，便于在 Zeebe 与日志中区分同一类型的多个工人实例。 */
    public SubmitPatientReferralWorker() {
        super("hospital-external-workers:" + JOB_TYPE);
    }

    /** 中文：返回本工人订阅的作业类型，基类据此注册 Zeebe 作业工人并接收该类型的作业。 */
    @Override
    public String jobType() {
        return JOB_TYPE;
    }

    /**
     * 中文：处理一次"转诊机构拟制转诊单"作业：确定关联句柄、登记转诊摘要，并把
     * referralReference 等变量写回流程，供紧随其后的消息抛出事件装配消息负载。
     */
    @Override
    protected void handle(JobContext ctx) {
        // 中文：patientId 是必填输入，缺失会让本次作业以校验错误结束，提示上游数据不完整。
        String patientId = ctx.requireString("patientId");
        // 中文：关联句柄若已存在就沿用，保证同一次转诊在重试或人工补录后仍归到同一条链路上；
        // 中文：不存在时才按患者号推导，而不是每次作业都换一个新值。
        String episodeId = ctx.findString("episodeId").orElseGet(() -> Ids.episode(patientId));
        // 中文：转诊编号是本次跨池往返的关联键，因此同样只在缺失时生成一次，绝不覆盖既有值。
        String referralReference = ctx.findString("referralReference")
                .orElseGet(Ids::referral);
        // 中文：收件机构缺失时退化为中性描述，保证摘要与审计记录不会为空。
        String organisation = ctx.findString("referringOrganisation").orElse("referring organisation");

        // 中文：写回本步骤的输出。referralStatus 记录拟制状态，便于在 Operate 中直接看出
        // 中文：转诊单已经准备好但尚未发出（发出由下一个消息抛出事件负责）。
        ctx.set("episodeId", episodeId)
           .set("referralReference", referralReference)
           .set("referralStatus", "composed")
           .set("referralComposedAt", Instant.now().toString())
           .note("composed referral " + referralReference + " for " + organisation);

        // 中文：按关联句柄把转诊摘要归档（集合名 referrals），与流程变量互为印证，
        // 中文：使"转诊单拟制"这一动作在引擎之外也留有可核对的记录。
        HospitalStore.get().put(episodeId, "referrals", referralReference, Map.of(
                "referralReference", referralReference,
                "patientId", patientId,
                "organisation", organisation,
                "composedAt", Instant.now().toString()));
    }
}
