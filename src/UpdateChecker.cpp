#include "UpdateChecker.h"

#include <QCoreApplication>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QStandardPaths>
#include <QLoggingCategory>
#include <QDebug>

#ifndef METABUILDER_CHANNEL
#define METABUILDER_CHANNEL "dev"
#endif
#ifndef METABUILDER_UPDATE_REPO
#define METABUILDER_UPDATE_REPO ""
#endif
#ifndef METABUILDER_TAG_PREFIX
#define METABUILDER_TAG_PREFIX ""
#endif

namespace {

// Assets are published as metabuilder-qt6-<version>-<os>-<arch>.<ext>, e.g.
// metabuilder-qt6-0.1.11-macos-universal.dmg. Matching on extension alone is
// not enough: the Windows build is a .zip too, so a macOS client looking only
// for ".dmg or .zip" can happily pick the Windows archive. Require the OS
// token, then score by architecture.
int assetScore(const QString &nameIn)
{
    const QString name = nameIn.toLower();

#if defined(Q_OS_MACOS)
    if (!name.contains(QLatin1String("macos"))
        && !name.contains(QLatin1String("darwin")))
        return -1;
    // A universal binary runs on either arch, so it is always acceptable.
    if (name.contains(QLatin1String("universal")))
        return 100;
#elif defined(Q_OS_WIN)
    if (!name.contains(QLatin1String("windows"))
        && !name.contains(QLatin1String("win")))
        return -1;
#else
    if (!name.contains(QLatin1String("linux")))
        return -1;
#endif

#if defined(Q_PROCESSOR_ARM)
    const QLatin1String wanted("arm64");
    const QLatin1String other("x86_64");
#else
    const QLatin1String wanted("x86_64");
    const QLatin1String other("arm64");
#endif
    if (name.contains(wanted))
        return 90;
    if (name.contains(other))
        return -1;   // built for the wrong CPU -- do not offer it
    return 50;       // no arch in the name; assume it is portable
}

} // namespace

UpdateChecker::UpdateChecker(QObject *parent)
    : QObject(parent)
    , m_net(new QNetworkAccessManager(this))
    , m_currentVersion(QCoreApplication::applicationVersion())
{
    const QString channel = QStringLiteral(METABUILDER_CHANNEL);
    const QString repo = QStringLiteral(METABUILDER_UPDATE_REPO);
    m_enabled = (channel == QLatin1String("release")) && !repo.isEmpty();
    m_status = m_enabled
        ? QStringLiteral("Not checked yet")
        : QStringLiteral("Source build — updates are handled by rebuilding");
}

int UpdateChecker::compareVersions(const QString &a, const QString &b)
{
    const QString ca = a.startsWith(QLatin1Char('v')) ? a.mid(1) : a;
    const QString cb = b.startsWith(QLatin1Char('v')) ? b.mid(1) : b;
    const QStringList pa = ca.split(QLatin1Char('.'));
    const QStringList pb = cb.split(QLatin1Char('.'));
    const int n = qMax(pa.size(), pb.size());
    for (int i = 0; i < n; ++i) {
        const int va = i < pa.size() ? pa.at(i).section(QLatin1Char('-'), 0, 0).toInt() : 0;
        const int vb = i < pb.size() ? pb.at(i).section(QLatin1Char('-'), 0, 0).toInt() : 0;
        if (va != vb)
            return va < vb ? -1 : 1;
    }
    return 0;
}

void UpdateChecker::setStatus(const QString &s)
{
    m_status = s;
    emit stateChanged();
}

void UpdateChecker::check()
{
    if (!m_enabled || m_checking)
        return;

    m_checking = true;
    setStatus(QStringLiteral("Checking for updates…"));

    // Deliberately not /releases/latest: that returns the newest release in
    // the repo regardless of tag, and this repo also carries unrelated tags
    // with no Qt assets. Fetch the list and pick the newest matching tag.
    QNetworkRequest req(QUrl(QStringLiteral("https://api.github.com/repos/")
                             + QStringLiteral(METABUILDER_UPDATE_REPO)
                             + QStringLiteral("/releases?per_page=30")));
    // GitHub rejects API requests without a User-Agent.
    req.setRawHeader("User-Agent", "MetaBuilder-UpdateChecker");
    req.setRawHeader("Accept", "application/vnd.github+json");

    QNetworkReply *reply = m_net->get(req);
    connect(reply, &QNetworkReply::finished, this, [this, reply]() {
        onCheckFinished(reply);
    });
}

void UpdateChecker::onCheckFinished(QNetworkReply *reply)
{
    reply->deleteLater();
    m_checking = false;

    if (reply->error() != QNetworkReply::NoError) {
        setStatus(QStringLiteral("Update check failed: ") + reply->errorString());
        emit failed(reply->errorString());
        return;
    }

    const QString prefix = QStringLiteral(METABUILDER_TAG_PREFIX);
    const QJsonArray releases =
        QJsonDocument::fromJson(reply->readAll()).array();

    QJsonObject best;
    QString bestVersion;
    for (const QJsonValue &v : releases) {
        const QJsonObject r = v.toObject();
        if (r.value(QStringLiteral("draft")).toBool())
            continue;
        const QString tag = r.value(QStringLiteral("tag_name")).toString();
        if (!prefix.isEmpty() && !tag.startsWith(prefix))
            continue;
        const QString ver = tag.mid(prefix.size());
        if (bestVersion.isEmpty() || compareVersions(ver, bestVersion) > 0) {
            bestVersion = ver;
            best = r;
        }
    }

    if (bestVersion.isEmpty()) {
        setStatus(QStringLiteral("No published release found"));
        return;
    }

    m_latestVersion = bestVersion;
    m_releasePageUrl = QUrl(best.value(QStringLiteral("html_url")).toString());

    m_assetUrl.clear();
    m_assetName.clear();
    int bestScore = 0;
    const QJsonArray assets = best.value(QStringLiteral("assets")).toArray();
    for (const QJsonValue &v : assets) {
        const QJsonObject a = v.toObject();
        const QString name = a.value(QStringLiteral("name")).toString();
        const int score = assetScore(name);
        if (score > bestScore) {
            bestScore = score;
            m_assetName = name;
            m_assetUrl = QUrl(a.value(
                QStringLiteral("browser_download_url")).toString());
        }
    }

    m_updateAvailable =
        compareVersions(m_latestVersion, m_currentVersion) > 0;
    setStatus(m_updateAvailable
        ? QStringLiteral("Version %1 is available").arg(m_latestVersion)
        : QStringLiteral("Up to date (%1)").arg(m_currentVersion));
    qInfo().noquote() << "UpdateChecker:" << m_status
                      << (m_assetName.isEmpty()
                            ? QStringLiteral("(no matching asset)")
                            : QStringLiteral("asset=") + m_assetName);
}

void UpdateChecker::download()
{
    if (!m_updateAvailable || m_downloading)
        return;
    if (m_assetUrl.isEmpty()) {
        // Nothing matched for this platform; the release page is still useful.
        openReleasePage();
        return;
    }

    const QString dir = QStandardPaths::writableLocation(
        QStandardPaths::DownloadLocation);
    const QString target = QDir(dir).filePath(m_assetName);

    m_downloading = true;
    m_downloadPercent = 0;
    setStatus(QStringLiteral("Downloading %1…").arg(m_assetName));

    QNetworkRequest req(m_assetUrl);
    req.setRawHeader("User-Agent", "MetaBuilder-UpdateChecker");
    req.setAttribute(QNetworkRequest::RedirectPolicyAttribute,
                     QNetworkRequest::NoLessSafeRedirectPolicy);

    QNetworkReply *reply = m_net->get(req);
    connect(reply, &QNetworkReply::downloadProgress, this,
            [this](qint64 got, qint64 total) {
        m_downloadPercent = total > 0 ? int((got * 100) / total) : 0;
        emit stateChanged();
    });
    connect(reply, &QNetworkReply::finished, this, [this, reply, target]() {
        reply->deleteLater();
        m_downloading = false;

        if (reply->error() != QNetworkReply::NoError) {
            setStatus(QStringLiteral("Download failed: ")
                      + reply->errorString());
            emit failed(reply->errorString());
            return;
        }

        QFile out(target);
        if (!out.open(QIODevice::WriteOnly)) {
            setStatus(QStringLiteral("Could not write ") + target);
            emit failed(out.errorString());
            return;
        }
        out.write(reply->readAll());
        out.close();

        setStatus(QStringLiteral("Downloaded to ") + target);
        emit downloadFinished(target);
        // Reveal rather than install: replacing a running bundle is a
        // separate problem, and the user can drop it into /Applications.
        QDesktopServices::openUrl(QUrl::fromLocalFile(QFileInfo(target).absolutePath()));
    });
}

void UpdateChecker::openReleasePage()
{
    if (m_releasePageUrl.isValid())
        QDesktopServices::openUrl(m_releasePageUrl);
}
