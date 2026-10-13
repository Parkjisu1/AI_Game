## Latest actual server audit — 2026-09-21 18:05 KST

User entered their Ubuntu password in the visible SSH window opened locally by Open-NewPlay-QA.ps1. Password was not captured. QA key authentication now works. Key restricted to172.31.28.47 with restrict and expiry20260921125357Z (=21:53:57KST). No new sudo grant. Existing default operator key was also rejected earlier; interactive password login was the successful route. Do NOT repeat that physical attendance is required merely to regain SSH.

- Actual host: sameHP, kernel7.0.0-31, continuous uptime3days sinceSept18 16:55. Current8containers running, web/Mongohealthy, localhostlogin200/protectedAPIs401/gatewayhealth200/Qdranthealth200. All sourceHEADs/gateway+composehashes match prior tested version; web/watcher trees clean. No production code/config/restart/reboot changes.
- Sept19,20,21 daily04:30backups all loggedcomplete/success at04:32, all3external completionmarkers exist. LatestSept21T043003 all4files fullySHA256verified bothnative/external, manifests identical. Restored TODAY's externalMongoarchive into isolatednetwork-none/tmpfsMongo:21collections1016documents content/index/optionsmatch. Removedtestcontainer. DifferencefromSept18's1018docs is onlyhermes_workers3->1, consistentwith24hourstale-worker cleanupsource. No othercollectioncountdrop.
- Tasks26,in_progress0,accepted-unlearned0,learningerrors0,freshwatcherheartbeat50seconds. PersonalClaude tokenfiles0,profiles0,sessions0. Qdrantgreen7176points,modelbge-m3present. LitellmURLmissing. No claim of actualteamAI completion.
- Disk764GiBinternal/571GiBexternalfree; dpkgclean,failedunits0; currentUSBmouse/keyboard/externalenumerated; lockfalse,idle0,ACsleepnothing. CurrentbootearlyNVMeAPST/ACPIerrors persist; no newcrashfile and currentbooterrorqueryhasno laterpanic. PhysicalHPpowercycle/kernelrootcause remainsUNVERIFIED, VMrebootdoesnotcloseit.
- OldmigrationexpiryserviceactuallyranSept19 02:45:47-48; oldkeymarker/sudoersabsent. The user's manualattempts left2malformedQApublickeylines(emptyexpiry+typos); removedonlyexactlinesafterbackup, preservedvalid4hourkeyandothers, freshSSHPASS. backup ~/.ssh/authorized_keys.before-qa-malformed-cleanup-20260921.
- TailscaleSTILLNeedsLogin/registerunexpectedEOF despiteworkingprotocolhandshakeandcontrolHTTPS. CrucialcurrentServeconfigis{} andno443listener; loginapprovalalonewillNOTestablishteamHTTPS/WSS. Publichostnamepointsold100.111.77.39,newregisteredpeer100.72.201.90offline. TechnicalregistrationandServe/hostname/wssroutingremainunfinished. Recipients handletheir ownaccountapprovals; donotasksendertodootherpeople'saccounts.
- Updated authoritative report E:/AI/qa/newplay-completion-check-20260921/REPORT.md (alsoCURRENT-REPORT.md); oldmorningreportpreservedREPORT-before-access.md. Evidence server-*.log inthatfolder. Existingr2handoffZIPnotmodified(deliveryexcluded). Historic13Python/9CLI/browser/deploy/VMrestoretestswerenotallreruntoday; exacttestedsourceversionconfirmedandnewoperational/backupchecksperformed.

## Earlier completion audit — 2026-09-21 before access recovery

User requested a complete check of whether all work other than delivery is done. Read-only checks found it is NOT complete. Current pinned-host SSH to newplay@172.31.29.251 rejects the prior migration key (Permission denied); expiry was Sept19 02:45:47KST. Host matches prior HP MAC C8-5A-CF-02-63-FF and responds to SSH. Do not infer power-off or claim cleanup timer execution without access.

Operator Tailscale Running; new Ubuntu peer newplay-1.tailf6f809.ts.net/100.72.201.90 Offline, last seen2026-09-18T07:46:50.1Z. Team hostname newplay.tailf6f809.ts.net still resolves100.111.77.39; HTTPS /login from operator PC fails curl28 after~5s. Public HTTPS/WSS is not passed. Existing Sept18 logs (13Python/9CLI, browser, deployment, freshOSrecovery/reboot) reread and retained as HISTORICAL passes only. PhysicalHPboot, Sept19-21scheduledbackups and current8services/source/queue/logs remain unverified. No product/config/account changes or reboot performed.

Report: E:/AI/qa/newplay-completion-check-20260921/REPORT.md, evidence current-observations.json. Read-only server collection script prepared in that folder but NOT run. Async question pending: can someone execute commands at Ubuntu terminal, or is a permanent SSH method available? Do not ask sender to log into recipient accounts. Need actual access to continue internal audit; do not work around expired authorization blindly.

## Previous follow-up — 2026-09-18 20:01 KST

- Latest user asked to continue unfinished work. Completed fresh Ubuntu KVM recovery drill without changing production source/config or restarting production services. Recipient accounts remain recipient-owned. Physical-screen availability question has no answer; HP was NOT rebooted.
- Fresh official Ubuntu24.04 image hash verified; guest kernel6.8.0-139, Docker29.8.0/Compose5.5.1. QEMU/cloud-image-utils installed on native host. Guest external network restricted BEFORE real data/secrets restoration; original backup read-only. Guest-only SSH on host127.0.0.1:12222.
- Restored entire20260918T180601backup:7images, completeappstate, sameweb/watchercommits, guestDockerGID988. Mongo21collections/1018documents exact; Qdrant7176points; actual bge-m3 embedding1024dims and search passed. HTTP permission/opt-out/revocation, two actual WebSocket sessions UID1000/sameworktree/replaydenial/isolation/sessioncommits passed. Synthetic artifacts removed. Test task collection typo corrected and actual pixelforge_tasks26/zeroactive checked.
- Guest OS reboot changed boot_id, all8services automatically returned, web/Mongohealthy, login200/API401, cleanapplytree, failedunits0. Guest then gracefully shut down. Native19:57original8serviceshealthy, sourcecommits/DockerGID984unchanged, backupenabled, dpkgclean, failedunits0.
- Guest disk retained at /home/newplay/migration-20260918/recovery-lab (mode700) as stopped QA evidence; not auto-started. Never restart with unrestricted networking because it now contains real secrets. Guest private key not packaged. Backup timer unit files checked but guest timer intentionally not enabled. This validates fresh-OS full application restoration, NOT HP physical kernel/USB/BIOS stability.
- Tailscale protocol IPv4TCP443 Noise handshake/whoami passed19:40 and AuthURL issuance18:32 observed. Still NeedsLogin19:57 with coordination warning and register request:unexpected end of JSON input. Technical registration issue remains, in addition to recipient approval. Do not call it fixed or ask sender to perform recipients' account actions.
- Updated full operator ZIP r2 built, all50entries SHA256/CRC verified native, Windows copy verified. Path E:/AI/scripts/newplay/handoff/newplay-operator-handoff-20260918-r2.zip;7,018,076,766bytes;SHA25683abf16fe1a98f5c94db11cc136abf1ba57f187f61d358e5073291bf31fd82aa. External copy also SHA256 verified; native-copy-operator-r2.log reports EXTERNAL_OPERATOR_R2_ZIP_HASH_VERIFIED. All three copies match. r1 preserved; r2 is the single complete latest handoff, no extra r1 package needed. Developer source ZIP unchanged; outer updated reports supersede its older status text.
- Evidence FOLLOWUP-20260918.md, recovery-guest-*.log, native-followup-final.log. Remaining technical Tailscale/publicrouting, realrecipientGoogle/Claude/adminaccess, physicalHPbootstability, configuredexternalfeatures. Temporary migrationSSH/sudo expires2026-09-19 02:45:47KST; permanentoperatoraccess required.


## Operator full ZIP delivered — 2026-09-18 18:44 KST

User explicitly clarified that recipients must handle their own accounts; do not ask the sender to log in or approve for them. New task: package all operator handoff files into one ZIP. Completed without changing production code/config or restarting services.

- Final Windows ZIP: E:/AI/scripts/newplay/handoff/newplay-operator-handoff-20260918.zip
- Native copy: /home/newplay/NewPlay-handoff-20260918/newplay-operator-handoff-20260918.zip
- External copy: /media/newplay/Expansion/NewPlay-handoff-20260918/newplay-operator-handoff-20260918.zip
- Size 7,018,047,839 bytes, 40 outer ZIP entries, ZIP64, unencrypted operator-only (real secrets and production data included).
- SHA256 9d100c71bc413d0e666be57a815716a1f575d2a3f566acfe6f497def019619be. All ZIP members SHA256/CRC checked on server; four runtime backup artifacts match original trusted manifest; Windows and external copies match whole ZIP hash.
- Contents: validated native backup 20260918T180601 (full state, seven Docker images, logical Mongo, DB fingerprint and original checksums), exact developer review ZIP/source/tools, operator guides, current QA results/screenshots, backup tools, historical audit reports/findings. The root guide states account approval belongs to recipients/current account admins, and Tailscale/real-account/boot-stability acceptance is still pending. Old login links must not be reused.
- Sidecar checksum and readable operator README are next to Windows ZIP. Verification evidence: operator-package-local-verification.json, native-build-operator-package.log, native-copy-operator-package.log. Build helpers and document staging stay in this QA directory.
- Original Windows/WSL whole-machine exports and auditor SSH private keys/temporary sudo are NOT part of this operating handoff; all current native application state is included. Original backups remain untouched.
## Tailscale login follow-up — 2026-09-18 18:29 KST

User pressed Connect but browser spinner never reached confirmation. Native daemon also stuck in RegisterReq/NeedsLogin. General HTTPS/controlplane key endpoint and NTP pass; DERP netcheck reachable. Original auth request started16:59 and stalled. Restart + fresh login attempt now returns no AuthURL. A temporary TS_FORCE_NOISE_443=true override did not fix it. A separate memory-only userspace daemon also failed to issue an auth URL within15s; probe stopped. This does NOT establish the root cause (client, path, or upstream registration). Official status page reported operational during check.

Removed unsuccessful /run systemd override and restarted normal daemon, left login attempted. No node records, saved identities, or team settings deleted. Eight NewPlay services remain running. Original link /a/921162f01f517 belongs to the superseded attempt; do not keep sending it as a current working link. Need user browser/device detail and whether https://login.tailscale.com/admin loads with the existing team account before proceeding. Prior browser/device question pending. Do not claim browser cache or user error as cause. Evidence native-tailscale-*.log; official code v1.102.4/control/controlhttp/client.go documents the tested port443 knob.
# Latest measured state ? 2026-09-18 18:15 KST

This section supersedes all older state descriptions below. Read REPORT.md for the review result.

- Eight native Ubuntu Docker services running; web and Mongo healthy. Web login and gateway health HTTP 200. dpkg audit empty; no failed systemd units.
- SSH restored. Browser-only QA key and local tunnel removed after tests. Original migration key and temporary sudo remain until the configured 2026-09-19 02:45:47 KST cleanup deadline, pending permanent operator access.
- Latest verified full backup: /data/newplay-backups/20260918T180601 and /media/newplay/Expansion/NewPlay-native-backups/20260918T180601. Both hash checks passed; isolated Mongo logical restore 21 collections / 1018 docs exact content/index/options match; Qdrant cold volume startup/count/config/schema match; Git fsck and image archive read passed. Daily 04:30 backup timer enabled.
- Additional actual defect found in browser integration QA: gateway ensureWorktree global prune removed /data/apply/webstore metadata, invisible inside workbench. Removed gateway global prune and both watcher workspace.py global prunes. Restored only affected Git metadata from verified backup. Fixed root-owned intermediate directory created by partial extraction. Actual terminal creation and cleanup now preserve deployment tree; two namespace regression tests pass.
- Final web commit 43fac1bc460dcf6b24b6a6ddce63fb3ee20a0940. Watcher final commit starts 0d36997 (full value in handoff/SERVER-SOURCE.json). Gateway archive exact source hash recorded there.
- Packaged tests rerun: 13 Ubuntu Python behavioral tests, 9 Windows CLI tests, web permissions VM checks all pass. Real browser renders four pages and executes shell UID1000 through a local proxy/SSH tunnel with a synthetic identity. Browser JS errors zero. Not real OAuth or public WSS.
- Synthetic identity/profile/sessions/worktree/branch/home cleaned; deployment worktree intact. Actual deployment/revert probes retained as audit history.
- During this turn our gateway recreation omitted --env-file .env.compose, giving wrong Docker group 999. Corrected via explicit env file to group984, Docker API verified, browser retested. Use explicit env file for all future compose mutations.
- Final developer review ZIP: E:/AI/scripts/newplay/handoff/newplay-hub-native-ubuntu-20260918-review.zip, 248 files, 916906 bytes, SHA256 14c1be4a7a701ab78048e44ff7a31f41da2c03fc4fbd197295735786098381fc. Also in QA directory, Ubuntu ~/NewPlay-handoff-20260918/, and Expansion/NewPlay-handoff-20260918/. Exact server web/watcher/gateway/config files, tools, sanitized templates, report/tests/docs. Actual configured secret scan passed. Original ZIP unchanged.
- Popup was old recovered kernel package failure; report preserved/marked seen. Original boot kernel panic root cause and 6.8 successful boot remain unverified. Current kernel7.0.0-31; Mongo rseq workaround remains measured, not a vendor support claim. Do not reboot casually.
- Tailscale still Logged out at18:15. Await user finishing existing-team login/authorization via https://login.tailscale.com/a/921162f01f517 . Prior async clarification pending. Old Windows node owns original public hostname. Public HTTPS/WSS, real Google login, real personal Claude task and permanent operator rights are NOT verified. No personal Claude tokens restored. LiteLLM missing config displayed; external API/voice/design features not certified.
- Next: user Tailscale authorization and deliberate hostname/public reverse proxy validation, actual account walkthrough, permanent operator access/handoff, eventual boot stability/full blank-machine recovery exercise. Do not claim full handoff complete while these remain.

---

# NewPlay Ubuntu migration — connection preparation

## Authorized scope

User requested completion of the remaining Ubuntu/Docker migration, restoration, QA and handoff work. Fix confirmed defects only; no unrelated feature expansion. Ubuntu installation/login was performed by the user. The current operator workspace remains Windows AIMED, 172.31.28.47.

## Latest measured state — 2026-09-18 17:35 KST

- Native Ubuntu is logged in on 7.0.0-31-generic. No additional reboot attempted; 6.8 boot remains unverified. Original panic initiating cause remains unestablished.
- Canonical Mongo restored and exactly matched 21 collections / 1013 documents, including indexes/options. Compose snapshot preserved in a separate reference DB. Qdrant collection fingerprints and Ollama model verified.
- Mongo 8.3.11 runs with GLIBC_TUNABLES=glibc.pthread.rseq=1; isolated 1000-write/read test passed, serverStatus confirms per-thread allocator (usingPerCPUCaches=false). This is a measured workaround, not proof of vendor support for the host kernel.
- All eight native Compose services started. Web health and watcher/learner DB connectivity passed. Preview cloned separately, persistent Yarn project cache configured, baseline build produced 349 files.
- Web commit 43fac1b; watcher audited-fix commit df4392c, followed by harmless deployment QA commit ea128e6 and revert 43eafa0. Product apply QA bb0d1f6 reverted by 341bc82. Actual final source trees matched pre-probe trees.
- Linux: 11 behavioral regressions passed, including real isolated Mongo retry fairness. Web route permission tests passed; native Next build and gateway image build passed. Windows handoff CLI: 9 tests passed, including late working/index edits, local commits and another server deployment.
- Actual HTTP: unauthenticated API denial, four signed synthetic-session page responses, profile opt-out, terminal tickets, API role permissions, invalidated prior session/token after allowlist removal passed. This is not real Google OAuth validation.
- Actual WebSocket: two successful terminal command executions, UID1000, fixed worktree, replay rejection, internal-service isolation, internet access and start/end Git snapshot fields passed. Initial harness timeout was ANSI parsing (tmux capture confirmed commands had run), then corrected and rerun. Synthetic sessions, profile, worktree, branch and personal home cleaned; product apply worktree remained intact.
- Popup fully identified through desktop accessibility: update-notifier, “시스템 프로그램 오류를 발견했습니다. 오류를 보고하시겠습니까?”. Only report was the recovered 16:16 kernel package preinstall failure. dpkg --audit empty, relevant packages installed, no new kernel panic after login. Report preserved and marked seen; Cancel clicked without sending an external report. Follow-up accessibility tree showed the dialog gone. Future crash reporting retained.
- Full native backup systemd service started 17:31:33. Its completion and restore test are NOT yet confirmed. Timer files installed but NOT enabled yet. Backup stops application writers and data services for consistent archive, restarts them, saves all images, hashes files, copies to mounted Expansion if present. Must inspect service status and resume services if necessary before other QA.
- Tailscale remains NeedsLogin. Current URL https://login.tailscale.com/a/921162f01f517 . Public hostname and WSS route NOT restored/tested. Old offline Windows node owns original name. Real team Claude account still untested (no personal tokens restored).
- **REMOTE ACCESS TEMPORARILY BLOCKED BY OUR CHANGE:** browser tunnel preparation replaced restrict with restrict,port-forwarding,permitopen=...,permitlisten="none". Native SSH rejects the resulting key options. User has been told honestly and asked to run: `cp ~/migration-20260918/authorized-keys-before-browser ~/.ssh/authorized_keys`. Original settings are saved, ownership remains newplay. DO NOT reboot. Wait for user action; no remaining authenticated shell available. For future browser tunneling, use a separate temporary key while retaining the working migration key untouched.
- Remaining: inspect backup completion, restore probe, enable timer, browser render QA, Tailscale/Google external access, final source/config handoff archive and runbooks, permanent operator access and temporary credential cleanup. Legacy QA host-prune fix prepared in handoff/qa/legacy; old timestamp-less learning fixtures explicitly marked superseded.

## Earlier measured state — 2026-09-18 16:49 KST (superseded above)

- After the user's power cycle, SSH returned at 16:34 KST on **7.0.0-31-generic**. Mouse receiver, NVIDIA driver and Seagate Expansion were registered; the backup volume was mounted at /media/newplay/Expansion. No D-state tasks or failed services were observed; lock/sleep settings persisted.
- Saved EFI pstore records identify the 16:17 panic as **7.0.0-31-generic**, with `Fatal exception in interrupt` and `build_detached_freelist`. Earlier ACPI/global module waits are also present. This does not establish the initiating cause or prove durable hardware stability. The GA kernel had not been verified booted.
- Docker Engine **29.8.0**, Compose **5.5.1** installed from official repository; hello-world ran successfully. The newplay operator was added to the docker group.
- Copied **74 server artifacts / 9,123,154,821 bytes** from the external backup to /home/newplay/migration-20260918/backup. Source stream and destination SHA-256 matched the trusted original manifest. Excluded only the full WSL export and Windows-files archive, still preserved in both original backups.
- Extracted Linux backup into the isolated root-only migration staging directory. Loaded all seven original Docker images and matched their image IDs. Copied original deployment sources and selected /data/newplay directories into their native paths; live OS /etc, user session and SSH files were not overwritten.
- Configured one canonical stack (localhost web3000/gateway3001/mongo27018/qdrant6343/ollama11434), corrected docker group ID, and prepared the terminal public wss URL. Web, watcher, learner, ops and gateway have **not** been started.
- **Database restoration has not run.** Mongo image refuses kernel 7.0 startup (SERVER-121912); no logical archive was imported. Qdrant and Ollama initially ran, then were cleanly stopped for the next reboot. The restore script stopped before the restore stage. DO NOT rerun native-restore-data.sh from its beginning: fresh-path guards intentionally reject overwriting the already-copied deployment/data. Resume from the database-start/restore section after the kernel is compatible.
- Installed matching Ubuntu NVIDIA 595.91.07 modules for **6.8.0-139-generic**, rebuilt initramfs, and requested a normal reboot at **16:45:26 KST**, using the exact GRUB menu IDs for a one-time GA boot. Existing 7.0 default retained. SSH/ICMP have not returned by 16:49; physical screen status was requested. No confirmed GA boot yet.
- Tailscale installed (1.102.4). User completed registration at 16:46:50. Windows peer list shows Linux node **newplay-1.tailf6f809.ts.net**, **100.72.201.90**, because old offline Windows node still holds **newplay.tailf6f809.ts.net** /100.111.77.39. New peer reports Online but is not in the local engine/magicsock and Tailscale ping returns unknown peer; neither native LAN nor overlay SSH is confirmed after reboot. Do not claim public routing restored. Old public name requires deliberate reassignment after connectivity is recovered.
- Tailscale browser auto-open was rejected by execution policy; the user used the provided official login link instead. No bypass attempted.
- **Local source changes, not yet deployed:** fixed RA-04 with a shared Git-directory OS lock across deploy/rollback; fixed RA-05 by using the existing Git patch parser for product deletion/rename/binary paths and handling malformed patches. `test_targeted_fixes.py`: **4 passed** on Windows, including a separate-process lock test and failed-A/concurrent-B deployment case. Need Linux validation and deployment, then the remaining RA items.
- New evidence: native-recovered-check.log, native-docker-install.log, native-stage-backup.log, native-restoration-inspect.log, native-restore-data.log, native-tailscale-install.log, native-reboot-compatible.log. Additional manifests/fingerprints are on the server under migration-20260918. The entire previous pstore directory was copied there before the second reboot.

## Earlier state — 2026-09-18 16:21 KST (superseded above)

- Interactive SSH bootstrap succeeded at 16:12:57 KST. Key authentication and `sudo -n` were verified on the intended HP host (NIC C8-5A-CF-02-63-FF), native Ubuntu 24.04.5, user newplay UID/GID 1000, address 172.31.29.251.
- Screen locking was still enabled on inspection. Set lock-enabled=false, idle-delay=0 and AC sleep='nothing' in the actual user's session. Re-read confirmed false/0/nothing.
- Initial kernel: 7.0.0-31-generic. USB keyboard works; mouse receiver and Seagate Expansion were observed during enumeration in kernel logs, but never completed normal device registration. `lsblk` exposed only the internal SSD; this was not a filename/mount-path error.
- Kernel stacks show ACPI semaphore waits and global asynchronous module-loading waits. USB workers, multiple udev workers, NVIDIA initialization, thermald and newly requested modules were affected. The exact initiating firmware/kernel defect is not yet established.
- Installed official Ubuntu GA kernel 6.8.0-139-generic alongside the existing kernel. The installer initially blocked in intel-microcode's cpuid modprobe hook. cpuid had registered in /proc/devices but modprobe waited on the global asynchronous barrier. Terminated only the blocked pre-install shell, then recovered the package transaction with `apt-get --fix-broken install -y`; it succeeded. No package hook was edited or disabled. `dpkg --audit` was empty; initramfs and GRUB config were generated and checked.
- At 16:17:26 KST selected the GA kernel for ONE boot using grub-reboot and requested a normal systemctl reboot. Existing default retained for recovery. SSH and ICMP have not returned as of 16:21; the user was asked which screen is visible. Do not claim GA boot or hardware repair has succeeded.
- Docker is NOT installed. No application data has been restored and no product code changed in this turn. Native transfer/Docker setup scripts are prepared but have NOT been run.
- Next: obtain physical-screen state; distinguish shutdown hang from boot hang or changed address. Restore remote access, verify uname, kernel waits and USB enumeration before running native-docker-install.sh or transfer-native.py.
- Evidence: native-inventory.log, native-kernel-check.log, native-kernel-install.log, native-kernel-install-retry.log, native-reboot-ga.log. Package-recovery command output is in the conversation tool log. Full original kernel log is also preserved on Ubuntu at /home/newplay/migration-20260918/kernel-before.log.

## Historical connection preparation (superseded above)

- The former server LAN address 172.31.29.251 responds but refuses TCP 22.
- The old Windows Tailscale address 100.111.77.39 times out. The new host name does not resolve yet.
- No remote changes have been made to the newly installed Ubuntu.
- `F:/NewPlay-connect.sh` is ready for a one-time local execution on the new Ubuntu PC. Its local source is `NewPlay-connect.sh` alongside this document. Bash syntax and the external copy were checked.
- The script is specific to the HP Pavilion TG01, installed Ubuntu 24.04, and a regular local user. It rejects the WSL environment and live USB root filesystem.
- It installs SSH, authorizes a dedicated key from 172.31.28.47, and grants temporary passwordless sudo for migration. The public key expires at the time recorded in `connection-plan.json`. A persistent systemd timer removes the temporary key and sudoers entry at the same deadline, including after reboot. The operator must revoke them sooner when work finishes.
- The administrator password is entered only in the Ubuntu terminal. The public host-key fingerprint shown by the script is to be verified before the first SSH connection.
- No HTTP server, new Windows firewall exception, or public port forwarding was created.

## Preparation completed without server access

- Verified backup paths are E:/AI/backups/newplay-server-20260918 and F:/NewPlay-server-backup-20260918. Existing backup artifacts were not edited.
- Restored clean source checkouts from the verified Compose web and watcher Git bundles into `repos/`. Both HEADs match the cold snapshot. No product code was modified in these checkouts.
- Compared both Mongo archives in read-only mode, including every collection's document count against the already-verified snapshot fingerprints. See `database-document-comparison.json`.
- Both databases contain the same 26 task IDs. Only one task differs: the public database has three comments absent from the Compose database.
- Two shared API tokens are revoked in the public database but remain active in the Compose database. Restoring Compose data directly would incorrectly revive those tokens.
- Fifteen collections have identical snapshot fingerprints. Other differences are worker/session and deployment ledger history; no unique task exists only in Compose.

## Restoration decisions and next work

1. Verify the new host's identity, user/UID, installed root filesystem, storage, networking, clock and graphics. Configure updates and service power behavior.
2. Install compatible Docker Engine and Compose using the official package repository. The original engine was 29.8.0; check available versions and compatibility before selection.
3. Stage the archive away from live OS paths. Do not overwrite new Ubuntu `/etc`, its root filesystem, or the fresh user's SSH access with the old WSL filesystem.
4. Restore the **public/systemd Mongo snapshot as the canonical application database**. This preserves the real task comments and token revocations. Preserve the Compose snapshot as a separately named, non-operational reference database for its distinct history. These choices follow the observed data differences; do not activate both application stacks or merge token states blindly.
5. Restore source, project workspaces, images, Qdrant/Ollama data and explicit configuration. Resolve native Ubuntu paths, ownership and workbench networking before starting writers.
6. Reproduce and repair the confirmed RA-01 through RA-16 defects only. In particular, the PowerShell after-deploy hard reset must not erase edits made while waiting for a deployment.
7. Verify the actual public path, authentication/revocation, WebSocket terminal, opt-out behavior, deployment/rollback, learning isolation and backup restoration. Keep fake-CLI tests distinct from actual team-account AI completion.
8. Produce the corrected developer/operator handoff package, installation/runbook evidence and unresolved external-account requirements. Revoke the temporary migration key and administrator grant after permanent operator access is validated.

## Rules and references

Read E:/AI/AGENTS.md and its db-search/hallucination-prevention rules. Bootstrap and archive inspection helpers are NewPlay-specific operational utilities, under the project-specific exception to genre-code DB searches. No game code or game design was generated. The earlier explicit authorization governs this migration; no new approval is being requested. The required local connection step is a technical access boundary, not a policy or skill approval gate.

Primary references checked: Ubuntu OpenSSH server documentation; Docker Engine Ubuntu installation documentation; OpenBSD sshd authorized_keys restrictions and expiry; MongoDB mongo-tools archive.go/parser.go.


