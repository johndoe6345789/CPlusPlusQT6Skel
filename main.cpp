#include <QGuiApplication>
#include <QIcon>
#include <QQuickWindow>
#include <QTimer>
#include <QCommandLineParser>
#include <QImage>
#include <QQuickStyle>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QUrl>
#include <QDir>
#include <QCoreApplication>

#include "src/PackageRegistry.hpp"
#include "src/ModPlayer.hpp"
#include "src/DBALClient.h"
#include "src/PackageLoader.h"
#include "src/NodeRegistry.hpp"
#include "src/UpdateChecker.h"

#ifdef METABUILDER_SPARKLE
#include "src/SparkleUpdater.h"
#endif

int main(int argc, char *argv[]) {
    qputenv("QML_XHR_ALLOW_FILE_READ", "1");
    // Must precede any Controls instantiation. The platform styles (macOS,
    // iOS, Windows) are native-rendered and silently discard a Control's
    // custom background/contentItem -- which this codebase sets on every
    // CButton, CTextField and CSelect, so those customisations were being
    // thrown away wholesale. Basic honours them on every platform, which also
    // keeps the app looking the same across desktop and mobile.
    QQuickStyle::setStyle(QStringLiteral("Basic"));
    QGuiApplication app(argc, argv);
    app.setOrganizationName("MetaBuilder");
    app.setOrganizationDomain("metabuilder.local");
    app.setApplicationName("MetaBuilder");
    // Window/taskbar icon. macOS uses the bundle's .icns instead, but this is
    // what Linux and Windows read, and it also covers an unbundled build.
    app.setWindowIcon(QIcon(QStringLiteral(":/appicon-256.png")));
    app.setApplicationVersion(QStringLiteral(METABUILDER_VERSION));

#ifdef METABUILDER_SPARKLE
    // No-ops unless the bundle carries a feed URL and public key.
    updater::start();
#endif

    // Everything exposed to QML must outlive the engine. C++ destroys locals
    // in reverse declaration order, so the engine is declared *after* them --
    // otherwise teardown destroys the context objects first and any binding
    // still referencing them evaluates against a dangling pointer. That only
    // shows up on a clean quit, which is why it stayed hidden while the app
    // was always being killed.
    UpdateChecker updateChecker;

    // Runtime data lives in Contents/Resources once deployed, and in the
    // source tree for a plain build. Prefer the bundle so the .app stays
    // relocatable; SRCDIR only has to hold up on the machine that built it.
    const QString resourcesDir =
        QDir::cleanPath(QCoreApplication::applicationDirPath()
                        + QStringLiteral("/../Resources"));
    const bool bundled = QDir(resourcesDir
                              + QStringLiteral("/packages")).exists();

    // QML import path: the directory holding QmlComponents/qmldir, so Qt
    // resolves "import QmlComponents 1.0". Bundled builds get a real copy,
    // source builds go through the imports/QmlComponents symlink.
    const QString importsDir = QDir::cleanPath(
        bundled ? resourcesDir + QStringLiteral("/qml")
                : QStringLiteral(SRCDIR) + QStringLiteral("/imports"));

    const QString packagesDir = QDir::cleanPath(
        bundled ? resourcesDir + QStringLiteral("/packages")
                : QStringLiteral(SRCDIR) + QStringLiteral("/packages"));

    PackageRegistry registry;
    ModPlayer modPlayer;
    DBALClient dbalClient;
    PackageLoader packageLoader;
    NodeRegistry nodeRegistry;
    registry.loadPackage("frontpage");
    packageLoader.setPackagesDir(QDir(packagesDir).absolutePath());
    packageLoader.scan();
    packageLoader.setWatching(true);

    // Load workflow node type registry
    const QString registryPath = QDir::cleanPath(
        QStringLiteral(SRCDIR)
        + QStringLiteral(
            "/../../workflow/plugins/registry/node-registry.json"));
    nodeRegistry.loadRegistry(registryPath);

    QQmlApplicationEngine engine;
    if (QDir(importsDir).exists()) {
        engine.addImportPath(importsDir);
    }

    auto *ctx = engine.rootContext();
    ctx->setContextProperty(QStringLiteral("UpdateCheck"),     &updateChecker);
    ctx->setContextProperty(QStringLiteral("PackageRegistry"), &registry);
    ctx->setContextProperty(QStringLiteral("ModPlayer"),       &modPlayer);
    ctx->setContextProperty(QStringLiteral("DBALClient"),      &dbalClient);
    ctx->setContextProperty(QStringLiteral("PackageLoader"),   &packageLoader);
    ctx->setContextProperty(QStringLiteral("NodeRegistry"),    &nodeRegistry);

    // --capture drives the visual regression harness: render one view at a
    // fixed size, write a PNG, exit. Pair it with QT_QUICK_BACKEND=software
    // and QT_QPA_PLATFORM=offscreen so output is deterministic and headless --
    // GPU rasterisation differs between machines, which would make image
    // comparison useless.
    QString captureView, capturePath;
    QSize captureSize(1360, 860);
    for (int i = 1; i < argc; ++i) {
        const QString arg = QString::fromLocal8Bit(argv[i]);
        if (arg.startsWith(QStringLiteral("--capture-view=")))
            captureView = arg.section(QLatin1Char('='), 1);
        else if (arg.startsWith(QStringLiteral("--capture-out=")))
            capturePath = arg.section(QLatin1Char('='), 1);
        else if (arg.startsWith(QStringLiteral("--capture-size="))) {
            const QString v = arg.section(QLatin1Char('='), 1);
            captureSize = QSize(v.section(QLatin1Char('x'), 0, 0).toInt(),
                                v.section(QLatin1Char('x'), 1, 1).toInt());
        }
    }
    const bool capturing = !capturePath.isEmpty();

    const QUrl url(QStringLiteral("qrc:/qt/qml/DBALObservatory/App.qml"));
    QObject::connect(&engine, &QQmlApplicationEngine::objectCreated,
                     &app, [url, capturing, captureView, capturePath,
                            captureSize](QObject *obj, const QUrl &objUrl) {
                         if (!obj && objUrl == url) {
                             QCoreApplication::exit(-1);
                             return;
                         }
                         if (!capturing || objUrl != url)
                             return;

                         auto *window = qobject_cast<QQuickWindow *>(obj);
                         if (!window) {
                             qWarning("capture: root is not a QQuickWindow");
                             QCoreApplication::exit(2);
                             return;
                         }
                         window->resize(captureSize);
                         if (!captureView.isEmpty())
                             window->setProperty("currentView", captureView);

                         // Let bindings settle and the scene render before
                         // grabbing; a single event-loop turn is not enough
                         // for layouts that size themselves from content.
                         QTimer::singleShot(1500, window,
                                            [window, capturePath]() {
                             const QImage shot = window->grabWindow();
                             if (shot.isNull() || !shot.save(capturePath)) {
                                 qWarning("capture: failed to write %s",
                                          qPrintable(capturePath));
                                 QCoreApplication::exit(3);
                                 return;
                             }
                             QCoreApplication::quit();
                         });
                     }, Qt::QueuedConnection);

    updateChecker.check();

    engine.load(url);
    return app.exec();
}
