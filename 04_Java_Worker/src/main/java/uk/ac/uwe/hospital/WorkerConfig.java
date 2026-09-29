package uk.ac.uwe.hospital;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Properties;

/**
 * Runtime configuration for the worker fleet.
 *
 * <p>Precedence, lowest first: built-in defaults, {@code workers.properties} on
 * the working directory or the classpath, then environment variables. Nothing is
 * required for a local Camunda 8 Run cluster, which listens on plaintext
 * {@code localhost:26500}.
 *
 * <p>中文：这是工作器集群的运行时配置对象，把连接参数与并发参数收敛为单一入口。</p>
 * <p>中文：配置按“内置默认值 &lt; 类路径模板 &lt; 工作目录文件 &lt; 环境变量”逐层覆盖，
 * 因此本地 Camunda 8 Run 不做任何配置即可直接启动。</p>
 * <p>中文：环境变量以 HPAS_ 为前缀并把点号换成下划线，便于在容器或 CI 中临时调整单个参数，
 * 而不必重新打包 jar。</p>
 */
public final class WorkerConfig {

    /** 中文：内部属性表，承载内置默认值以及被逐层覆盖后的最终取值。 */
    private final Properties props = new Properties();

    /** 中文：构造过程本身就是一次“默认值 → 模板 → 本地文件 → 环境变量”的覆盖，之后不再变更。 */
    private WorkerConfig() {
        // 中文：默认值面向本地 Camunda 8 Run：明文 gRPC 的 127.0.0.1:26500，开箱即可运行。
        props.setProperty("gateway.address", "127.0.0.1:26500");
        props.setProperty("gateway.plaintext", "true");
        props.setProperty("worker.maxJobsActive", "8");
        props.setProperty("worker.timeoutSeconds", "30");
        props.setProperty("worker.pollIntervalMillis", "200");
        props.setProperty("worker.threads", "4");
        props.setProperty("failure.mode", "off");          // off | rules | all
        props.setProperty("failure.prefix", "");
        props.setProperty("store.retainInstances", "2000");
        // Precedence, lowest first: defaults, packaged template, working-directory
        // file, environment. An operator's local file must beat the template.
        // 中文：这三行的顺序不可调换：本地文件必须在模板之后，环境变量必须排在最后。
        loadFromClasspath();
        loadFrom(Path.of("workers.properties"));
        applyEnvironment();
    }

    /** 中文：唯一的取配置入口；构造完即返回，调用方拿到的已经是解析好的最终取值。 */
    public static WorkerConfig load() {
        return new WorkerConfig();
    }

    /** 中文：读取工作目录下的同名文件；文件不存在属于正常情况，因此直接返回而不报错。 */
    private void loadFrom(Path path) {
        // 中文：以“可读”作为存在性判断，顺便覆盖权限不足、路径是目录等边界情况。
        if (!Files.isReadable(path)) {
            return;
        }
        try (InputStream in = Files.newInputStream(path)) {
            props.load(in);
        } catch (IOException e) {
            // 中文：文件存在却读不了说明部署有问题，属于配置错误，应当快速失败。
            throw new IllegalStateException("cannot read " + path, e);
        }
    }

    /** 中文：读取打包在 jar 内的模板配置，为所有部署提供一份统一基线。 */
    private void loadFromClasspath() {
        try (InputStream in = WorkerConfig.class.getResourceAsStream("/workers.properties")) {
            // 中文：模板允许缺席，此时只用内置默认值，便于最小化部署。
            if (in != null) {
                props.load(in);
            }
        } catch (IOException e) {
            throw new IllegalStateException("cannot read classpath workers.properties", e);
        }
    }

    /** 中文：用环境变量做最后一次覆盖，优先级最高，适合容器化部署与 CI 临时调整。 */
    private void applyEnvironment() {
        // 中文：只改写已有键的值、不新增键，因此遍历过程中修改 Properties 是安全的。
        props.forEach((k, v) -> {
            String env = System.getenv(envName(String.valueOf(k)));
            // 中文：空字符串视为“未设置”，避免 CI 传了空变量反而清掉默认值。
            if (env != null && !env.isBlank()) {
                props.setProperty(String.valueOf(k), env);
            }
        });
    }

    /** 中文：把属性键映射为环境变量名，点号换成下划线并加 HPAS_ 前缀以防命名冲突。 */
    private static String envName(String key) {
        return "HPAS_" + key.toUpperCase().replace('.', '_');
    }

    /** 中文：网关 gRPC 地址，本地默认指向 127.0.0.1:26500。 */
    public String gatewayAddress() {
        return props.getProperty("gateway.address");
    }

    /** 中文：是否使用明文连接；Camunda 8 Run 与 docker-compose 为明文，SaaS 需要 TLS。 */
    public boolean plaintext() {
        return Boolean.parseBoolean(props.getProperty("gateway.plaintext"));
    }

    /** 中文：每个工作器的本地预取上限，直接决定对引擎施加的背压强度。 */
    public int maxJobsActive() {
        return Integer.parseInt(props.getProperty("worker.maxJobsActive"));
    }

    /** 中文：作业锁的租约时长；设得太短会让耗时作业在处理途中被引擎重新激活。 */
    public Duration jobTimeout() {
        return Duration.ofSeconds(Long.parseLong(props.getProperty("worker.timeoutSeconds")));
    }

    /** 中文：空闲时的长轮询间隔，在响应速度与网关压力之间取折中。 */
    public Duration pollInterval() {
        return Duration.ofMillis(Long.parseLong(props.getProperty("worker.pollIntervalMillis")));
    }

    /** 中文：工作器执行线程数，即同一进程内可并行处理的作业上限。 */
    public int workerThreads() {
        return Integer.parseInt(props.getProperty("worker.threads"));
    }

    /** 中文：故障注入模式，取值为 off / rules / all，只用于演示与演练。 */
    public String failureMode() {
        return props.getProperty("failure.mode");
    }

    /** 中文：故障注入的作业类型前缀，用于把演练范围限定在部分活动上。 */
    public String failurePrefix() {
        return props.getProperty("failure.prefix");
    }

    /**
     * Redacted view for the startup log.
     *
     * <p>中文：启动日志用的一行摘要，刻意只列出连接与并发参数，不输出任何凭据或密钥。</p>
     * <p>中文：当前缀为空时省略该字段，避免日志里出现无意义的空键值。</p>
     */
    public String describe() {
        return "gateway=" + gatewayAddress()
                + " plaintext=" + plaintext()
                + " maxJobsActive=" + maxJobsActive()
                + " jobTimeout=" + jobTimeout()
                + " pollInterval=" + pollInterval()
                + " threads=" + workerThreads()
                + " failureMode=" + failureMode()
                + (failurePrefix().isBlank() ? "" : " failurePrefix=" + failurePrefix());
    }
}
