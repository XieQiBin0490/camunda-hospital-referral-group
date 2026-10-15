package uk.ac.uwe.hospital.support;

import com.fasterxml.jackson.databind.ObjectMapper;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Statement;

/**
 * The worker's database: one embedded H2 file, created on first use.
 *
 * <p>Review item 1 asked for business data to be saved and read back. The workers already
 * kept the right records and the right relationships - an episode handle that ties
 * patient, referral, appointment, funding, payment and refund together, an appointment
 * index that stops the same appointment being confirmed twice, and a payment check that
 * stops the same charge being taken twice - but they kept them in a map that died with the
 * process. This class makes that state durable without changing what the workers do.
 *
 * <p><b>One connection, deliberately.</b> H2 normally allows several connections to one
 * file database, but acquiring its file lock is not permitted in every environment; where
 * the lock cannot be taken, H2 opens the database read-only, and a second connection in the
 * same process then fails to write. The worker therefore holds a single connection for the
 * life of the process and serialises access to it. A later process opening the same file
 * gets it read-only, which is exactly what reading back saved data needs.
 *
 * <p>The URL can be overridden with the {@code hospital.db.url} system property, which is
 * how the tests point at an in-memory database instead of the file.
 *
 * <p>中文：这是工作器的数据库，使用嵌入式 H2 文件库，首次使用时自动建库建表。整改清单第 1 项
 * 要求业务数据可保存可读取。工作者原先已经维护了正确的记录与关系：一个贯穿患者、转诊、预约、
 * 资金、付款与退款的关联句柄，一个防止同一预约被重复确认的预约索引，以及一个防止同一笔费用被
 * 重复收取的付款判重。但这些状态原本只存在于进程内存中，重启即失。本类把这些状态落到数据库，
 * 而不改变工作者的业务行为。
 *
 * <p>此处刻意只保留一条连接。H2 通常允许多条连接访问同一个文件库，但取得其文件锁并非在所有
 * 环境都被允许；一旦拿不到锁，H2 会把库以只读方式打开，于是同一进程内的第二条连接就无法写入。
 * 因此工作器在进程存活期间只持有一条连接，并对其访问串行化。后续进程打开同一个文件时会是只读的，
 * 而这正好满足“把已保存的数据读回来”的需要。数据库地址可用系统属性 hospital.db.url 覆盖，测试
 * 即以此指向内存库，避免污染运行库。
 */
public final class Database {

    /** 中文：覆盖数据库地址的系统属性名；测试用它指向内存库。 */
    public static final String URL_PROPERTY = "hospital.db.url";

    /**
     * 中文：默认数据库地址，落在工作目录下的 data 目录。刻意不加 AUTO_SERVER，
     * 因为它与 H2 默认的文件锁方式互斥，而本类本就只使用一条连接。
     */
    private static final String DEFAULT_URL = "jdbc:h2:file:./data/hospital-workstore";

    /** 中文：用户名与口令。嵌入式单机库，保留默认 sa 空口令，与集群自身的二级存储一致。 */
    private static final String USER = "sa";
    private static final String PASSWORD = "";

    /** 中文：JSON 序列化器，用于把工作者传入的映射持久化为文本。 */
    private static final ObjectMapper JSON = new ObjectMapper();

    /** 中文：进程内唯一连接；为 null 或已关闭时重新建立。 */
    private static Connection shared;

    /** 中文：工具类，不允许实例化。 */
    private Database() {
    }

    /** 中文：返回当前生效的数据库地址。 */
    public static String url() {
        return System.getProperty(URL_PROPERTY, DEFAULT_URL);
    }

    /** 中文：返回共享的 JSON 序列化器，供两个存储类使用，避免重复构造。 */
    public static ObjectMapper json() {
        return JSON;
    }

    /** 中文：一段使用连接的数据库操作，允许抛出受检异常，便于在 lambda 内直接写 JDBC。 */
    public interface Work<T> {
        T apply(Connection connection) throws Exception;
    }

    /**
     * 中文：取得进程内唯一连接，必要时建表。调用方不应关闭它——它随进程存活，
     * 关闭后再次获取会以只读方式重开，从而无法写入。
     */
    public static synchronized Connection connection() throws SQLException {
        if (shared == null || shared.isClosed()) {
            shared = DriverManager.getConnection(url(), USER, PASSWORD);
            createSchema(shared);
        }
        return shared;
    }

    /**
     * 中文：在共享连接上串行执行一段操作。H2 的连接不是线程安全的，而工作器是多线程的，
     * 因此这里以连接对象为锁，把并发访问排队。异常统一包装为运行时异常，并带上调用方给出的语义。
     */
    public static <T> T inConnection(String what, Work<T> work) {
        try {
            Connection c = connection();
            synchronized (c) {
                return work.apply(c);
            }
        } catch (Exception e) {
            throw new IllegalStateException(what, e);
        }
    }

    /**
     * Create the schema if it is not there yet.
     *
     * <p>中文：建表语句全部使用 IF NOT EXISTS，因此可以在每次启动时无条件执行。若当前连接是
     * 只读的（例如第二个进程打开同一个文件库），建表会失败，此时表必然已由先前的写入者创建，
     * 因此记录一条说明后继续，而不是让整个进程启动失败。
     */
    private static void createSchema(Connection c) {
        try (Statement s = c.createStatement()) {

            // 中文：业务记录表。一个关联句柄下按集合名与记录键定位一条记录，负载以 JSON 文本存放，
            // 因此新增业务字段无需改表结构。
            s.execute("""
                    CREATE TABLE IF NOT EXISTS record (
                      correlation_id VARCHAR(191) NOT NULL,
                      collection     VARCHAR(64)  NOT NULL,
                      record_key     VARCHAR(191) NOT NULL,
                      payload        CLOB         NOT NULL,
                      updated_at     TIMESTAMP    NOT NULL,
                      PRIMARY KEY (correlation_id, collection, record_key)
                    )""");

            // 中文：预约去重索引。主键即关联句柄加预约号，重复登记会在数据库层被拒绝。
            s.execute("""
                    CREATE TABLE IF NOT EXISTS appointment_index (
                      correlation_id        VARCHAR(191) NOT NULL,
                      appointment_reference VARCHAR(191) NOT NULL,
                      booking_id            VARCHAR(191),
                      PRIMARY KEY (correlation_id, appointment_reference)
                    )""");

            // 中文：尝试计数表。单独成表是为了让自增可以在一条 UPDATE 里原子完成，
            // 避免多个工作者并发重试时丢失计数。
            s.execute("""
                    CREATE TABLE IF NOT EXISTS attempt_counter (
                      correlation_id VARCHAR(191) NOT NULL,
                      activity       VARCHAR(191) NOT NULL,
                      attempts       INT          NOT NULL,
                      recorded_at    DATE         NOT NULL,
                      PRIMARY KEY (correlation_id, activity)
                    )""");

            // 中文：审计日志表，只追加。occurred_at 由写入瞬间决定，表上不提供更新入口。
            s.execute("""
                    CREATE TABLE IF NOT EXISTS audit_log (
                      seq                  BIGINT AUTO_INCREMENT PRIMARY KEY,
                      occurred_at          TIMESTAMP    NOT NULL,
                      actor                VARCHAR(191),
                      action               VARCHAR(191),
                      correlation_id       VARCHAR(191),
                      element_id           VARCHAR(191),
                      process_instance_key BIGINT,
                      detail               CLOB
                    )""");
        } catch (SQLException e) {
            System.out.println("[database] schema not created on this connection ("
                    + e.getMessage() + "); the tables must already exist, continuing read-only");
        }
    }

    /** 中文：仅供测试使用，关闭并丢弃当前连接，使下次访问重新建立。 */
    static synchronized void resetForTests() {
        try {
            if (shared != null && !shared.isClosed()) {
                shared.close();
            }
        } catch (SQLException ignored) {
            // 中文：测试收尾，关闭失败无需处理。
        }
        shared = null;
    }
}
