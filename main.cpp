#include <QGuiApplication>
#include <QIcon>
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

    QQmlApplicationEngine engine;

    // Exposed to QML as UpdateCheck. Inert on a source build.
    UpdateChecker updateChecker;
    engine.rootContext()->setContextProperty(
        QStringLiteral("UpdateCheck"), &updateChecker);
    updateChecker.check();

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
    if (QDir(importsDir).exists()) {
        engine.addImportPath(importsDir);
    }

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

    auto *ctx = engine.rootContext();
    ctx->setContextProperty(QStringLiteral("PackageRegistry"), &registry);
    ctx->setContextProperty(QStringLiteral("ModPlayer"),       &modPlayer);
    ctx->setContextProperty(QStringLiteral("DBALClient"),      &dbalClient);
    ctx->setContextProperty(QStringLiteral("PackageLoader"),   &packageLoader);
    ctx->setContextProperty(QStringLiteral("NodeRegistry"),    &nodeRegistry);

    const QUrl url(QStringLiteral("qrc:/qt/qml/DBALObservatory/App.qml"));
    QObject::connect(&engine, &QQmlApplicationEngine::objectCreated,
                     &app, [url](QObject *obj, const QUrl &objUrl) {
                         if (!obj && objUrl == url)
                             QCoreApplication::exit(-1);
                     }, Qt::QueuedConnection);

    engine.load(url);
    return app.exec();
}
