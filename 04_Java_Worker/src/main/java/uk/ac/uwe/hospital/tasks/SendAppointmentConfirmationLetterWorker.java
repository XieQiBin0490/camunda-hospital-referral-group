package uk.ac.uwe.hospital.tasks;

import uk.ac.uwe.hospital.AbstractWorker;
import uk.ac.uwe.hospital.JobContext;
import uk.ac.uwe.hospital.support.ExternalServices;
import uk.ac.uwe.hospital.support.HospitalStore;
import uk.ac.uwe.hospital.support.Ids;

import java.time.Instant;
import java.util.Map;

/**
 * {@code send-appointment-confirmation-letter} - issues the appointment letter
 * through the external correspondence service.
 *
 * <p>The case study ties this activity to a rule: a patient contacted by
 * telephone still receives the letter, and the letter is the record of the
 * appointment. The worker therefore records the channel and the reference, and
 * refuses to claim a dispatch when no appointment reference exists to put in it.
 *
 * <p>中文：本类服务于 BPMN 发送任务 T_SendAppointmentLetter（出具新患者预约确认信），
 * 作业类型为 {@code send-appointment-confirmation-letter}。它接在"确认预约并登记预约号"的
 * 人工任务之后，是预约成立后的标准书面告知：即使预约就在两周内、患者随后还会接到电话
 * （网关 G_WithinFourteenDays 的分支），确认信依然必须寄出，因为信函本身就是预约的书面记录。
 * 因此本工人必须持有 appointmentReference 才肯声称已发信——没有预约号可写进信里，
 * 只能说明上游人工环节尚未真正完成预约，属于输入缺陷而不是可以糊弄过去的细节。
 */
public class SendAppointmentConfirmationLetterWorker extends AbstractWorker {

    /** 中文：作业类型标识，必须与模型中 zeebe:taskDefinition 的 type 逐字一致，否则引擎不会派发作业。 */
    public static final String JOB_TYPE = "send-appointment-confirmation-letter";

    /** 中文：用"工人族名 + 作业类型"拼出订阅名，便于在 Zeebe 与日志中区分同一类型的多个工人实例。 */
    public SendAppointmentConfirmationLetterWorker() {
        super("hospital-external-workers:" + JOB_TYPE);
    }

    /** 中文：返回本工人订阅的作业类型，基类据此注册 Zeebe 作业工人并接收该类型的作业。 */
    @Override
    public String jobType() {
        return JOB_TYPE;
    }

    /**
     * 中文：处理一次"出具预约确认信"作业。要求已存在预约号，随后通过外部通信服务寄出信函，
     * 并写回凭证、投递渠道与预约号；没有预约号可写进信里时，宁可报输入缺陷也不谎称已发信。
     */
    @Override
    protected void handle(JobContext ctx) {
        // 中文：patientId 是必填输入，缺失即视为上游数据缺陷，以校验异常终止本次作业。
        String patientId = ctx.requireString("patientId");
        // 中文：预约号是确认信的实质内容，也是"信函即预约记录"这一规则的凭据：
        // 中文：它由上游确认预约的人工任务写入，缺失说明预约尚未真正成立，因此直接报输入缺陷。
        String appointmentReference = ctx.requireString("appointmentReference");
        // 中文：沟通偏好默认按邮寄处理。案例研究要求电话联系过的患者同样收到信函，
        // 中文：所以渠道只影响记录方式，不影响"是否发信"这个决定。
        String channel = ctx.findString("communicationPreference").orElse("post");
        // 中文：episodeId 缺失时按患者号推导，使信函记录也能归集到同一次就诊的档案下。
        String episodeId = ctx.findString("episodeId").orElseGet(() -> Ids.episode(patientId));

        // 中文：调用外部通信服务寄出信函，渠道固定为 letter、收件人按患者处理；
        // 中文：服务不可用会抛可重试异常，由引擎重试，绝不在此之前写回"已发信"。
        String reference = ExternalServices.Correspondence.dispatch("letter", patientId);

        // 中文：写回发信结果：appointmentLetterSent 标记动作完成，凭证、渠道与预约号共同说明
        // 中文："为哪个预约、以什么方式发过信"，是后续联系患者与审计核对的事实依据。
        ctx.set("episodeId", episodeId)
           .set("appointmentLetterSent", true)
           .set("appointmentLetterReference", reference)
           .set("appointmentLetterChannel", channel)
           .set("appointmentReference", appointmentReference)
           .set("appointmentLetterSentAt", Instant.now().toString())
           .note("issued appointment letter " + reference + " for " + appointmentReference + " by " + channel);

        // 中文：按 episodeId 归集信函记录（集合名 letters，键为凭证号），只保存引用性字段，
        // 中文：不写入信函正文等临床内容，符合数据最小化要求，也便于管理报表统计发信数量。
        HospitalStore.get().put(episodeId, "letters", reference, Map.of(
                "reference", reference,
                "appointmentReference", appointmentReference,
                "channel", channel,
                "sentAt", Instant.now().toString()));
    }
}
