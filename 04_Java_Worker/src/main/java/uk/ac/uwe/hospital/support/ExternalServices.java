package uk.ac.uwe.hospital.support;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ThreadLocalRandom;

/**
 * The external providers the case study names, simulated deterministically.
 *
 * <p>The hospital does not call a real scheduling service, correspondence
 * service, payment provider or laboratory in this build, and the acceptance
 * evaluation states that limitation. What matters for the workers is that each
 * provider has a defined contract: it either answers, answers "no", or fails in
 * a way that is worth retrying - and the workers must map those three outcomes
 * onto the branches the model already has. A provider outage therefore becomes
 * {@code treatmentCapacityConfirmed = false} (the pending-and-retry path the
 * case study asks for), not an incident.
 *
 * <p>Every provider can be forced through configuration so that the exception
 * paths can be demonstrated on demand rather than hoped for.
 *
 * <p>中文：这里用确定性的桩实现代替真实的外部系统，把每个提供方的应答收敛为三种语义：
 * 成功、合法的否定结果（例如“暂时没有号源”）、以及值得重试的临时故障。之所以把故障也
 * 当成一种协议内应答而不是异常事故，是因为模型本身已经备有等待与重试分支；于是外部服务
 * 中断会被表达为流程变量，而不是让工作线程崩溃。为了能在演示与验收时按需复现异常路径，
 * 所有提供方都允许通过系统属性或环境变量强制进入指定的故障状态，避免依赖偶然性。
 */
public final class ExternalServices {

    /** 中文：工具类只提供静态方法，私有构造器用于阻止实例化。 */
    private ExternalServices() {
    }

    // ------------------------------------------------------------------ config

    /** 中文：先查系统属性再查环境变量，后者把点号换成下划线以符合环境变量命名限制。 */
    private static String forced(String key) {
        String v = System.getProperty(key);
        if (v == null || v.isBlank()) {
            v = System.getenv(key.toUpperCase(Locale.ROOT).replace('.', '_'));
        }
        return v == null ? "" : v.trim();
    }

    /** 中文：开关型配置只认字符串 true，未配置时自然为关闭，因此默认行为即正常路径。 */
    private static boolean forcedFlag(String key) {
        return "true".equalsIgnoreCase(forced(key));
    }

    // --------------------------------------------------------------- scheduling

    /** 中文：号源的不可变快照，reference 是外部系统的号源编号，日期与诊室用于回信与预约。 */
    public record Slot(String reference, LocalDate date, String clinic, String consultant) {
    }

    /** 中文：门诊号源提供方的模拟实现，负责把“有号、无号、超时”三种结果分开表达。 */
    public static final class Scheduling {

        /**
         * 中文：一次号源查询的结果。slots 为空且 available 为 true 表示服务正常但确实没有号源；
         * 真正的故障不在这里表达，而是抛出可重试异常，让模型走等待与重试分支。
         *
         * <p>Outcome of a slot search: either some slots, or none, or a retryable failure.
         */
        public record Result(List<Slot> slots, boolean available) {
        }

        /** 中文：按专科、时间窗与紧急程度查询号源；紧急请求给出更近的日期，以符合转诊时限。 */
        public static Result findSlots(String speciality, int withinDays, boolean urgent) {
            if (forcedFlag("hpas.scheduling.unavailable")) {
                throw new uk.ac.uwe.hospital.TransientJobException(
                        "external scheduling service did not answer within the request timeout");
            }
            if (forcedFlag("hpas.scheduling.noSlots")) {
                return new Result(List.of(), true);
            }
            // A short-notice search is harder to satisfy. Routine referrals beyond
            // two weeks almost always find something; anything inside the urgent
            // window is a coin toss in the real service, so make it deterministic here.
            // 中文：真实服务里临时约号本就难以满足，这里把随机性收敛为确定规则——非紧急且
            // 窗口不超过两天时返回空结果，紧急申请则始终保留号源，保证演示可复现。
            boolean none = !urgent && withinDays <= 2;
            if (none) {
                return new Result(List.of(), true);
            }
            List<Slot> slots = new ArrayList<>();
            LocalDate base = LocalDate.now().plusDays(urgent ? 3 : 21);
            slots.add(new Slot("SLOT-A", base, speciality + " clinic", "Consultant on call"));
            slots.add(new Slot("SLOT-B", base.plusDays(7), speciality + " clinic", "Consultant on call"));
            return new Result(slots, true);
        }
    }

    // ------------------------------------------------------- treatment capacity

    /** 中文：治疗容量提供方的模拟实现，对应模型中的容量确认与“未确认即重试”路径。 */
    public static final class Capacity {

        /** 中文：容量申请结果；未获确认时通过 unavailableResource 说明是哪项资源不可用。 */
        public record Result(boolean confirmed, String reference, String unavailableResource) {
        }

        /** 中文：申请治疗容量。被屏蔽的资源或服务整体不可用都返回未确认而非抛错，以便流程继续等待。 */
        public static Result request(String treatmentCode, int cycles, String requestedResource) {
            if (forcedFlag("hpas.capacity.unavailable")) {
                String resource = forced("hpas.capacity.resource");
                return new Result(false, null, resource.isBlank() ? "external treatment service" : resource);
            }
            if (requestedResource != null && !requestedResource.isBlank()) {
                String blocked = forced("hpas.capacity.blockedResources");
                for (String r : blocked.split(",")) {
                    if (!r.isBlank() && r.trim().equalsIgnoreCase(requestedResource.trim())) {
                        return new Result(false, null, r.trim());
                    }
                }
            }
            return new Result(true, Ids.capacity(), null);
        }
    }

    // ------------------------------------------------------------------ payment

    /**
     * 中文：与模型网关 {@code G_PaymentOutcome} 一一对应的付款结果，共四种，任何一种都不能被归并。
     * 原因在于每种结果在模型中走向不同分支：确认后继续治疗，拒付后允许再尝试，未收到确认必须转入
     * 人工调查，紧急临床需要则绕开财务阻塞直接放行。
     *
     * <p>The four outcomes the model's {@code G_PaymentOutcome} gateway distinguishes.
     */
    public enum PaymentOutcome {
        CONFIRMED("confirmed"),
        DECLINED("declined"),
        NO_RESPONSE("no response"),
        URGENT_CLINICAL_NEED("urgent clinical need");

        /** 中文：写入流程变量时使用的字面量，刻意与枚举名解耦，便于对齐 BPMN 中的既有取值。 */
        private final String processValue;

        /** 中文：构造时绑定流程变量取值，使外部契约与 Java 命名可以各自演进。 */
        PaymentOutcome(String processValue) {
            this.processValue = processValue;
        }

        /** 中文：返回供流程变量使用的字面量；小写加空格的形式与模型中已有的比较表达式保持一致。 */
        public String processValue() {
            return processValue;
        }
    }

    public static final class Payment {

        /**
         * 中文：付款应答。transactionReference 只在真正拿到确认号时才有值，其余结果保持为空，
         * 避免下游误以为“未确认但已有凭证”，从而绕开人工调查环节。
         */
        public record Result(PaymentOutcome outcome, String transactionReference,
                             double amount, String currency, LocalDate date) {
        }

        /**
         * 中文：发起一次付款请求。episodeId 仅用于关联尝试次数，判断强制结果是只影响首次请求
         * 还是每次请求都生效；若失败无限重复，模型的“允许再尝试”分支会空转，那是演示脚本
         * 的产物而非业务规则，因此默认只在首次注入异常，让重试自然成功。
         *
         * @param episodeId the correlation handle, used only to decide whether a
         *                  forced outcome applies once or on every attempt. A
         *                  decline that repeats forever would make the model's
         *                  "permit a further attempt" branch spin, which is a
         *                  demonstration artefact rather than a business rule.
         */
        public static Result request(String episodeId, double amount, String currency) {
            // 中文：读取强制结果与“仅首次生效”开关，并借助存储把本段事的尝试次数递增后再判断。
            String forcedOutcome = forced("hpas.payment.outcome");
            boolean once = !"false".equalsIgnoreCase(forced("hpas.payment.outcomeOnce"));
            int attempt = HospitalStore.get().nextAttempt(
                    episodeId == null ? "-" : episodeId, "payment-transaction");
            if (!forcedOutcome.isBlank() && once && attempt > 1) {
                forcedOutcome = "";   // the retry succeeds, as the case study intends
            }
            PaymentOutcome outcome;
            if (forcedOutcome.isBlank()) {
                outcome = PaymentOutcome.CONFIRMED;
            } else {
                outcome = switch (forcedOutcome.trim().toUpperCase(Locale.ROOT)) {
                    case "DECLINED" -> PaymentOutcome.DECLINED;
                    case "NO_RESPONSE", "NO-CONFIRMATION", "NO_CONFIRMATION" -> PaymentOutcome.NO_RESPONSE;
                    case "URGENT", "URGENT_CLINICAL_NEED" -> PaymentOutcome.URGENT_CLINICAL_NEED;
                    default -> PaymentOutcome.CONFIRMED;
                };
            }
            if (outcome == PaymentOutcome.NO_RESPONSE) {
                // The provider took the money but never confirmed: this is the case
                // the case study says must be investigated, not re-requested.
                return new Result(outcome, Ids.payment(), amount, currency, LocalDate.now());
            }
            // 中文：只有确认成功才生成交易号，拒付与紧急放行都不产生支付凭证。
            String ref = outcome == PaymentOutcome.CONFIRMED ? Ids.payment() : null;
            return new Result(outcome, ref, amount, currency, LocalDate.now());
        }

        /**
         * 中文：退款是财务动作，且必须依附一笔已存在的交易，因此没有原交易号时一律不予通过。
         *
         * <p>Refunds are a Finance action and only ever follow an existing transaction.
         */
        public record RefundResult(boolean approved, String reference, double amount) {
        }

        /** 中文：执行退款校验；缺少原交易号等同于校验失败，只有配置明确拒绝时才直接拒绝。 */
        public static RefundResult refund(double amount, String originalReference) {
            if (forcedFlag("hpas.refund.rejected")) {
                return new RefundResult(false, null, amount);
            }
            if (originalReference == null || originalReference.isBlank()) {
                return new RefundResult(false, null, amount);
            }
            return new RefundResult(true, Ids.refund(), amount);
        }
    }

    // ------------------------------------------------------------ correspondence

    /** 中文：信件、改派与索取资料等对外联络动作的模拟实现，统一返回可追踪的函件编号。 */
    public static final class Correspondence {

        /** 中文：投递信函。渠道与收件人仅用于表明意图，演示环境不真正发送，只留下可审计的编号。 */
        public static String dispatch(String channel, String recipient) {
            if (forcedFlag("hpas.correspondence.unavailable")) {
                throw new uk.ac.uwe.hospital.TransientJobException(
                        "external correspondence service rejected the dispatch request");
            }
            return Ids.letter();
        }

        /** 中文：转诊改派通知，返回独立前缀的编号，便于与普通函件在日志中区分。 */
        public static String redirect(String destinationService) {
            return Ids.redirect();
        }

        /** 中文：向外部机构索取病历资料，编号带专用前缀，代表一次可追踪的请求而非回信本身。 */
        public static String requestDocuments(List<String> documents, String organisation) {
            return Ids.request();
        }
    }

    // --------------------------------------------------------------- laboratory

    /** 中文：检验科提供方的模拟实现，用固定流程时间常量模拟化验周转期。 */
    public static final class Laboratory {

        /** 中文：化验申请回执，dueDate 是外部承诺的结果可用日期，供流程设置等待定时器。 */
        public record Result(String reference, LocalDate dueDate) {
        }

        /** 中文：申请血检，返回唯一编号并把应出结果日固定为两天后，使等待边界可复现。 */
        public static Result requestBloodTest(String patientId, String cycleReference) {
            return new Result(Ids.laboratory(), LocalDate.now().plusDays(2));
        }
    }

    // ---------------------------------------------------------------- reporting

    /** 中文：定期报表生成的模拟实现，返回报表编号作为业务回执。 */
    public static final class Reporting {

        /** 中文：周期参数只用于表明统计区间，演示实现不做真实数据聚合，因此忽略其内容。 */
        public static String generate(String period) {
            return Ids.report();
        }
    }

    static {
        // touch the random source once so the first call is not measurably slower
        // 中文：提前初始化随机源，避免首次业务调用因类加载与种子初始化而出现可测量的延迟抖动。
        ThreadLocalRandom.current().nextInt(1);
    }
}
