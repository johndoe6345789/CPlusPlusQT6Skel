#ifndef UPDATECHECKER_H
#define UPDATECHECKER_H

#include <QObject>
#include <QString>
#include <QUrl>

class QNetworkAccessManager;
class QNetworkReply;

// Checks whether a newer release binary exists and, on request, downloads it.
//
// Deliberately does nothing for a source build. METABUILDER_CHANNEL is "dev"
// unless the release script overrides it, so a developer running their own
// build is never told to "update" to something older than the tree they are
// sitting on.
class UpdateChecker : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool enabled READ enabled CONSTANT)
    Q_PROPERTY(QString currentVersion READ currentVersion CONSTANT)
    Q_PROPERTY(bool checking READ checking NOTIFY stateChanged)
    Q_PROPERTY(bool updateAvailable READ updateAvailable NOTIFY stateChanged)
    Q_PROPERTY(QString latestVersion READ latestVersion NOTIFY stateChanged)
    Q_PROPERTY(QString status READ status NOTIFY stateChanged)
    Q_PROPERTY(bool downloading READ downloading NOTIFY stateChanged)
    Q_PROPERTY(int downloadPercent READ downloadPercent NOTIFY stateChanged)

public:
    explicit UpdateChecker(QObject *parent = nullptr);

    bool enabled() const { return m_enabled; }
    QString currentVersion() const { return m_currentVersion; }
    bool checking() const { return m_checking; }
    bool updateAvailable() const { return m_updateAvailable; }
    QString latestVersion() const { return m_latestVersion; }
    QString status() const { return m_status; }
    bool downloading() const { return m_downloading; }
    int downloadPercent() const { return m_downloadPercent; }

    // Compares dotted numeric versions, ignoring a leading "v". Returns >0 if
    // a is newer than b, <0 if older, 0 if equal. Missing components count as
    // zero so "1.2" and "1.2.0" compare equal.
    static int compareVersions(const QString &a, const QString &b);

public slots:
    // No-op on a dev build. Safe to call repeatedly.
    void check();
    // Downloads the release asset to the user's Downloads folder and reveals
    // it. Does not replace the running bundle -- swapping a running app is a
    // separate problem, and unzipping into /Applications by hand is a
    // two second job.
    void download();
    void openReleasePage();

signals:
    void stateChanged();
    void downloadFinished(const QString &path);
    void failed(const QString &message);

private:
    void setStatus(const QString &s);
    void onCheckFinished(QNetworkReply *reply);

    QNetworkAccessManager *m_net = nullptr;
    bool m_enabled = false;
    bool m_checking = false;
    bool m_updateAvailable = false;
    bool m_downloading = false;
    int m_downloadPercent = 0;
    QString m_currentVersion;
    QString m_latestVersion;
    QString m_status;
    QUrl m_assetUrl;
    QString m_assetName;
    QUrl m_releasePageUrl;
};

#endif // UPDATECHECKER_H
