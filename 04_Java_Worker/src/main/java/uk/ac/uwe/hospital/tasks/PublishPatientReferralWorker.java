package uk.ac.uwe.hospital.tasks;

import uk.ac.uwe.hospital.AbstractWorker;
import uk.ac.uwe.hospital.JobContext;
import uk.ac.uwe.hospital.support.HospitalStore;
import uk.ac.uwe.hospital.support.Ids;
import uk.ac.uwe.hospital.support.MessagePublisher;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * {@code referring-org-publish-patient-referral} - the worker behind the message
 * throw event {@code RO_SendReferral} in the referring organisation's pool.
 *
 * <p>This is the pool-to-pool hop. Camunda 8 does not correlate a message for a
 * throw event; it creates a <em>job</em> and waits for a job worker to publish.
 * When this worker publishes the message {@code Patient referral}, the hospital
 * pool's message start event {@code E_ReferralReceived} fires and a
 * {@code PR_Operational_Merged} instance begins - a new instance in a different
 * pool, started by this one.
 *
 * <p>The correlation key is {@code referralReference}, deliberately: the
 * hospital process is started by three models that all declare the same start
 * message, and Camunda 8 refuses to start a second instance for a
 * {@code correlationKey} that already has one active. That makes the referral
 * idempotent - a retried job cannot multiply referrals.
 *
 * <p>中文：本工作器是 BPMN 中消息抛出事件 RO_SendReferral 的执行者，也是整条链路上
 * 真正跨池的那一跳。Camunda 8 不会替抛出事件去关联消息，它只生成一个作业并等待工作器
 * 完成发布。本工作器发出"Patient referral"之后，医院池的消息启动事件 E_ReferralReceived
 * 被触发，另一个池里的 PR_Operational_Merged 实例由此开始。
 *
 * <p>中文：关联键刻意选用 referralReference。因为三个模型声明了同一条启动消息，
 * 而 Camunda 8 对已经存在活动实例的关联键会拒绝再起第二个实例，于是转诊天然具备幂等性：
 * 作业重试不会制造出多份转诊。
 */
public class PublishPatientReferralWorker extends AbstractWorker {

    /** 中文：作业类型标识，必须与模型中 zeebe:taskDefinition 的 type 逐字一致，否则引擎不会派发作业。 */
    public static final String JOB_TYPE = "referring-org-publish-patient-referral";

    /**
     * 中文：消息名必须与医院池消息启动事件所引用消息的名称逐字一致，
     * 否则订阅无法匹配，转诊永远启动不了医院侧的实例。
     */
    public static final String MESSAGE_NAME = "Patient referral";

    /** 中文：用"工人族名 + 作业类型"拼出订阅名，便于在 Zeebe 与日志中区分同一类型的多个工人实例。 */
    public PublishPatientReferralWorker() {
        super("hospital-external-workers:" + JOB_TYPE);
    }

    /** 中文：返回本工人订阅的作业类型，基类据此注册 Zeebe 作业工人并接收该类型的作业。 */
    @Override
    public String jobType() {
        return JOB_TYPE;
    }

    /**
     * 中文：处理一次"发出患者转诊"作业：按关联键组装消息负载并发布，随后把消息键与发送
     * 状态写回流程。发布失败只降级为告警并记为未发送，不会让本作业失败，因为医院池可能
     * 尚未部署，那属于环境问题而不是本次转诊的缺陷。
     */
    @Override
    protected void handle(JobContext ctx) {
        // 中文：转诊编号是必需的：没有它就没有关联键，消息要么发不出去，要么会重复起实例。
        String referralReference = ctx.requireString("referralReference");
        // 中文：患者号是医院侧启动实例后立即要用到的输入，因此也作为必填项校验。
        String patientId = ctx.requireString("patientId");
        // 中文：关联句柄与收件机构沿用既有值，缺失时按同一套规则推导，保证两侧口径一致。
        String episodeId = ctx.findString("episodeId").orElseGet(() -> Ids.episode(patientId));
        String organisation = ctx.findString("referringOrganisation").orElse("referring organisation");

        // 中文：显式构造负载而不直接透传全部变量，使跨池契约保持窄而明确：
        // 中文：对方实例只会收到这几个字段，避免把本池的内部变量意外泄漏过去。
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("patientId", patientId);
        payload.put("episodeId", episodeId);
        payload.put("referralReference", referralReference);
        payload.put("referringOrganisation", organisation);
        // 中文：转诊紧迫度若已登记则一并传递，供医院侧的排程判断使用；未登记就不传，
        // 中文：让对方按自己的缺省规则处理，而不是替它编造一个值。
        ctx.findString("referralUrgency").ifPresent(v -> payload.put("referralUrgency", v));

        long messageKey = MessagePublisher.publish(
                MESSAGE_NAME, referralReference, episodeId, payload);

        // 中文：写回发送结果。referralStatus 区分"已发出"与"发送受阻"，
        // 中文：messageKey 是消息确实进入引擎的凭证；两者都不是"已被对方处理"的证据，
        // 中文：被接收这件事由医院侧自己的记录证明。
        ctx.set("referralStatus", messageKey >= 0 ? "sent" : "send-blocked")
           .set("referralMessageKey", messageKey)
           .set("referralSentAt", Instant.now().toString())
           .note(messageKey >= 0
                   ? "published '" + MESSAGE_NAME + "' key=" + messageKey + " correlationKey=" + referralReference
                   : "could not publish '" + MESSAGE_NAME + "' for " + referralReference);

        // 中文：不论发布是否成功都归档这次尝试，使"发过但没成功"也能被事后审计发现，
        // 中文：而不是只留下成功的记录、把失败悄悄丢掉。
        HospitalStore.get().put(episodeId, "referralMessages", referralReference, Map.of(
                "messageName", MESSAGE_NAME,
                "messageKey", messageKey,
                "correlationKey", referralReference,
                "published", messageKey >= 0,
                "attemptedAt", Instant.now().toString()));
    }
}
