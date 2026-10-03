# Encrypted configuration backups

Keep one private configuration folder per project, outside its public Git checkout. Register those folders in **Configs & backups**. Local Control does not inspect their values for display.

The original local-copy backend remains available: it creates private, hash-verified snapshots but does not encrypt their contents. The optional [restic integration](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html) supports encrypted local repositories, SFTP, S3 and restic’s other backends. Install restic through its [official installation instructions](https://restic.readthedocs.io/en/stable/020_installation.html); its binary is not bundled or silently installed.

## Configure once

1. Choose **Configure encryption** and enter the repository location.
2. Set a private password-file path, or the **name** of an existing environment variable containing the password. Never paste the password into the dashboard. Backend credentials remain in normal OS environment/configuration, outside the public checkout.
3. Initialize a new repository, or verify an existing one. Keep a separate, recoverable copy of the password; the application cannot recover a lost encryption key.
4. Enable the encrypted backend. **Create verified backup** and scheduled backups now use restic. The normal backup preview still lists selected source folders and estimated size; the encryption panel identifies the remote/local restic destination.

The child process receives credentials in its environment or through restic’s password-file option. Raw command errors and repository output are not copied to public logs. `RESTIC_PASSWORD_COMMAND` is not inherited. See restic’s [scripting and credential reference](https://restic.readthedocs.io/en/stable/075_scripting.html).

After an encrypted backup, Local Control runs a repository metadata check. That is not a full read of every stored data blob. Run **Restore encrypted snapshot** regularly: it restores into a new private directory and invokes restic’s content verification. Existing application configuration is never overwritten; manually inspect the result before changing a project mapping.

## Retention

**Review retention** previews the snapshots that exceed your selected keep-last count. Only this controller’s unique tag group is considered. Applying requires the same settings, inventory and preview; changed snapshots require another review. Other hosts’ backups remain outside that scope. Deleted snapshot data is reclaimed only when you separately run restic `prune`; Local Control does not automatically prune.

## Schedules and recovery

The default schedule is off. Enable the desired interval in backup settings. The running controller checks for due work every minute. A durable short reservation distinguishes pending work from an actually started backup. Queue rejection and failures record an error and retry with bounded backoff, starting at one minute; they do not consume the entire daily interval. Interrupted reservations recover after expiry.

For backups while Local Control is closed, choose **Schedule outside the dashboard**. This registers an explicit per-user task:

| Platform | Scheduler | Availability |
| --- | --- | --- |
| Windows | Task Scheduler, least privilege | User logged in; catch-up after sleep |
| macOS | User LaunchAgent | User logged in |
| Linux | systemd user timer | User manager running |

The OS task invokes `backup --due` and uses the same private settings, locks and schedule ledger. A password file is usually easier for scheduled restic jobs than a terminal-only environment variable. Disable the OS task through the same dialog. Relocating state preserves the original forwarding location, but verify an OS task after moving its executable or Python environment.

These schedules do not run before user login or while a computer is off. A successful snapshot is not a disaster-recovery plan: retain a copy on another disk or machine and verify restoration.
