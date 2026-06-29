"use client";
import { useEffect, useState } from "react";

interface AssigneeRow {
  assignee: string;
  email: string;
  webhook_url: string;
  slack_user_id: string;
}

export default function SettingsPage() {
  const [defaultUrl, setDefaultUrl] = useState("");
  const [hasDefault, setHasDefault] = useState(false);
  const [maskedDefault, setMaskedDefault] = useState("");
  const [botToken, setBotToken] = useState("");
  const [hasBotToken, setHasBotToken] = useState(false);
  const [maskedBotToken, setMaskedBotToken] = useState("");
  const [assignees, setAssignees] = useState<AssigneeRow[]>([]);
  const [notifyCreate, setNotifyCreate] = useState(true);
  const [notifyStatus, setNotifyStatus] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string>("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  // 허용 사용자 (관리자 전용)
  const [isAdmin, setIsAdmin] = useState(false);
  const [allowedDbEmails, setAllowedDbEmails] = useState<string[]>([]);
  const [allowedEnvEmails, setAllowedEnvEmails] = useState<string[]>([]);
  const [newAllowedEmail, setNewAllowedEmail] = useState("");
  const [allowedBusy, setAllowedBusy] = useState(false);

  // 감사 로그 (관리자 전용)
  interface AuditEntry {
    task_id?: string | null;
    event: string;
    actor: { email: string; source: string };
    data?: Record<string, unknown>;
    created_at: string;
  }
  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([]);

  useEffect(() => { reload(); reloadAllowed(); reloadAudit(); }, []);

  async function reloadAudit() {
    try {
      const res = await fetch("/api/admin/audit?limit=100");
      if (!res.ok) return;
      const j = await res.json();
      if (Array.isArray(j.entries)) setAuditEntries(j.entries);
    } catch { /* ignore */ }
  }

  async function reloadAllowed() {
    try {
      const res = await fetch("/api/admin/allowed-users");
      if (res.status === 403 || res.status === 401) {
        setIsAdmin(false);
        return;
      }
      if (!res.ok) return;
      const j = await res.json();
      setIsAdmin(true);
      setAllowedDbEmails(Array.isArray(j.emails) ? j.emails : []);
      setAllowedEnvEmails(Array.isArray(j.envEmails) ? j.envEmails : []);
    } catch {
      setIsAdmin(false);
    }
  }

  async function addAllowedEmail() {
    const email = newAllowedEmail.trim();
    if (!email) return;
    setAllowedBusy(true);
    try {
      const res = await fetch("/api/admin/allowed-users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(j.error || "추가 실패");
        return;
      }
      setNewAllowedEmail("");
      await reloadAllowed();
      flash(`${j.email} 추가됨`);
    } finally {
      setAllowedBusy(false);
    }
  }

  async function removeAllowedEmail(email: string) {
    if (!confirm(`${email}의 접근 권한을 회수합니다.`)) return;
    setAllowedBusy(true);
    try {
      const res = await fetch(
        `/api/admin/allowed-users?email=${encodeURIComponent(email)}`,
        { method: "DELETE" }
      );
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        setError(j.error || "제거 실패");
        return;
      }
      await reloadAllowed();
      flash(`${email} 제거됨`);
    } finally {
      setAllowedBusy(false);
    }
  }

  function reload() {
    fetch("/api/settings")
      .then((r) => r.json())
      .then((j) => {
        if (j.ok) {
          setHasDefault(j.hasDefault || false);
          setMaskedDefault(j.settings?.slack_webhook_url || "");
          setHasBotToken(j.hasBotToken || false);
          setMaskedBotToken(j.settings?.slack_bot_token || "");
          setAssignees((j.settings?.slack_assignee_webhooks || []).map((w: AssigneeRow) => ({
            assignee: w.assignee,
            email: w.email || "",
            webhook_url: w.webhook_url || "",
            slack_user_id: w.slack_user_id || "",
          })));
          setNotifyCreate(j.settings?.slack_notify_on_create !== false);
          setNotifyStatus(j.settings?.slack_notify_on_status_change !== false);
        }
      })
      .catch(() => {});
  }

  function flash(msg: string) {
    setNotice(msg);
    setTimeout(() => setNotice(""), 2500);
  }

  function addRow() {
    setAssignees((prev) => [...prev, { assignee: "", email: "", webhook_url: "", slack_user_id: "" }]);
  }

  function removeRow(idx: number) {
    setAssignees((prev) => prev.filter((_, i) => i !== idx));
  }

  function updateRow(idx: number, patch: Partial<AssigneeRow>) {
    setAssignees((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      const body: Record<string, unknown> = {
        slack_notify_on_create: notifyCreate,
        slack_notify_on_status_change: notifyStatus,
        slack_assignee_webhooks: assignees.map((r) => ({
          assignee: r.assignee.trim(),
          email: r.email.trim().toLowerCase(),
          webhook_url: r.webhook_url,
          slack_user_id: r.slack_user_id.trim(),
        })),
      };
      if (defaultUrl.trim()) body.slack_webhook_url = defaultUrl.trim();
      if (botToken.trim()) body.slack_bot_token = botToken.trim();

      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        setError(j.error || "저장 실패");
        return;
      }
      flash("저장됨");
      setDefaultUrl("");
      setBotToken("");
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setSaving(false);
    }
  }

  async function testDefault() {
    setTesting("default");
    setError("");
    try {
      const body: Record<string, string> = {};
      if (defaultUrl.trim()) body.webhook_url = defaultUrl.trim();
      const res = await fetch("/api/slack/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await res.json();
      if (j.ok) flash("기본 webhook 전송 성공");
      else setError(`전송 실패: ${j.error}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "전송 실패");
    } finally {
      setTesting("");
    }
  }

  async function testRowDM(row: AssigneeRow, idx: number) {
    if (!row.slack_user_id.trim()) {
      setError("User ID를 입력하세요");
      return;
    }
    if (!hasBotToken && !botToken.trim()) {
      setError("Bot Token을 먼저 저장하세요");
      return;
    }
    // 만약 botToken을 새로 입력했지만 아직 저장 안 했으면 먼저 저장
    if (botToken.trim() && !hasBotToken) {
      await save();
    }
    setTesting(`row-${idx}`);
    setError("");
    try {
      const res = await fetch("/api/slack/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slack_user_id: row.slack_user_id.trim() }),
      });
      const j = await res.json();
      if (j.ok) flash(`${row.assignee || "row"} DM 전송 성공`);
      else setError(`전송 실패: ${j.error}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "전송 실패");
    } finally {
      setTesting("");
    }
  }

  async function testRowWebhook(row: AssigneeRow, idx: number) {
    if (!row.webhook_url || row.webhook_url.startsWith("***")) {
      setError("새 Webhook URL을 입력하거나 저장 후 task로 검증하세요");
      return;
    }
    setTesting(`row-${idx}`);
    setError("");
    try {
      const res = await fetch("/api/slack/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ webhook_url: row.webhook_url }),
      });
      const j = await res.json();
      if (j.ok) flash(`${row.assignee || "row"} webhook 전송 성공`);
      else setError(`전송 실패: ${j.error}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "전송 실패");
    } finally {
      setTesting("");
    }
  }

  async function clearDefault() {
    if (!confirm("기본 webhook URL 삭제?")) return;
    setSaving(true);
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slack_webhook_url: "" }),
      });
      reload();
      flash("기본 webhook 삭제됨");
    } finally { setSaving(false); }
  }

  async function clearBotToken() {
    if (!confirm("Bot Token 삭제?")) return;
    setSaving(true);
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slack_bot_token: "" }),
      });
      reload();
      flash("Bot Token 삭제됨");
    } finally { setSaving(false); }
  }

  return (
    <div>
      <div className="mb-5">
        <h1 className="text-xl sm:text-2xl font-bold">설정</h1>
        <p className="text-sm text-gray-500 mt-1 leading-relaxed">팀원 접근 권한 및 Slack 알림</p>
      </div>

      {/* 허용 사용자 (관리자 전용) */}
      {isAdmin && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 max-w-3xl mb-4">
          <h2 className="text-base font-bold mb-1">👥 허용 사용자</h2>
          <p className="text-xs text-gray-500 mb-4">
            여기 있는 Google 계정만 로그인 가능합니다. env 목록은 서버 부트스트랩용(편집 불가),
            DB 목록은 아래에서 관리하세요.
          </p>

          {allowedEnvEmails.length > 0 && (
            <div className="mb-3">
              <p className="text-xs text-gray-400 mb-1">env 화이트리스트 (고정)</p>
              <div className="flex flex-wrap gap-1.5">
                {allowedEnvEmails.map((e) => (
                  <span
                    key={`env-${e}`}
                    className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded border border-gray-200"
                    title="env ALLOWED_EMAILS — 서버 설정에서만 변경 가능"
                  >
                    🔒 {e}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="mb-3">
            <p className="text-xs text-gray-400 mb-1">DB 화이트리스트 ({allowedDbEmails.length}명)</p>
            {allowedDbEmails.length === 0 ? (
              <p className="text-xs text-gray-400 italic">아직 추가된 사용자가 없습니다.</p>
            ) : (
              <ul className="space-y-1">
                {allowedDbEmails.map((e) => (
                  <li
                    key={e}
                    className="flex items-center gap-2 text-sm border border-gray-200 rounded px-3 py-2"
                  >
                    <span className="flex-1 text-gray-700">{e}</span>
                    <button
                      onClick={() => removeAllowedEmail(e)}
                      disabled={allowedBusy}
                      className="text-xs text-red-600 hover:bg-red-50 px-2 py-1 rounded disabled:opacity-40"
                    >
                      제거
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="flex gap-2">
            <input
              type="email"
              value={newAllowedEmail}
              onChange={(e) => setNewAllowedEmail(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") addAllowedEmail(); }}
              placeholder="추가할 이메일 (예: alice@gameberry.co.kr)"
              className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm"
              style={{ color: "#e6e9ef" }}
            />
            <button
              onClick={addAllowedEmail}
              disabled={allowedBusy || !newAllowedEmail.trim()}
              className="px-4 py-2 text-sm bg-black text-white rounded-lg hover:bg-gray-800 disabled:opacity-40"
            >
              추가
            </button>
          </div>
        </div>
      )}

      {/* 감사 로그 (관리자 전용) */}
      {isAdmin && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 max-w-3xl mb-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-base font-bold">📜 감사 로그 (최근 {auditEntries.length}건)</h2>
            <button onClick={reloadAudit} className="text-xs text-blue-600 hover:underline">
              새로고침
            </button>
          </div>
          <p className="text-xs text-gray-500 mb-3">
            누가 언제 어떤 태스크/설정을 바꿨는지 기록. 삭제 불가 (append-only).
          </p>
          {auditEntries.length === 0 ? (
            <p className="text-xs text-gray-400 italic">기록된 이벤트가 아직 없습니다.</p>
          ) : (
            <div className="max-h-96 overflow-y-auto border border-gray-100 rounded">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="text-left px-2 py-1.5 font-medium text-gray-500">시각</th>
                    <th className="text-left px-2 py-1.5 font-medium text-gray-500">이벤트</th>
                    <th className="text-left px-2 py-1.5 font-medium text-gray-500">행위자</th>
                    <th className="text-left px-2 py-1.5 font-medium text-gray-500">상세</th>
                  </tr>
                </thead>
                <tbody>
                  {auditEntries.map((e, i) => (
                    <tr key={i} className="border-t border-gray-100 hover:bg-gray-50">
                      <td className="px-2 py-1.5 text-gray-500 whitespace-nowrap">
                        {new Date(e.created_at).toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}
                      </td>
                      <td className="px-2 py-1.5 font-mono">
                        <span className="bg-gray-100 px-1.5 py-0.5 rounded">{e.event}</span>
                      </td>
                      <td className="px-2 py-1.5 text-gray-700">
                        <span className="text-[10px] text-gray-400 mr-1">[{e.actor.source}]</span>
                        {e.actor.email || "-"}
                      </td>
                      <td className="px-2 py-1.5 text-gray-600 truncate max-w-xs" title={JSON.stringify(e.data)}>
                        {JSON.stringify(e.data || {}).slice(0, 100)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Bot Token (전역) */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 max-w-3xl mb-4">
        <h2 className="text-base font-bold mb-1">🤖 Slack Bot Token</h2>
        <p className="text-xs text-gray-500 mb-4">
          이 토큰이 있으면 작업자에게 봇 이름으로 DM이 갑니다 (Webhook 방식의 &quot;발신자=설치자&quot; 문제 해결).
        </p>
        <div className="flex items-center gap-2">
          <input
            type="password"
            value={botToken}
            onChange={(e) => setBotToken(e.target.value)}
            placeholder={hasBotToken ? `현재: ${maskedBotToken} (변경하려면 새 토큰 입력)` : "xoxb-..."}
            className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm font-mono"
            style={{ color: "#e6e9ef" }}
          />
          {hasBotToken && (
            <button onClick={clearBotToken} className="px-2.5 py-2 text-xs text-red-600 hover:bg-red-50 rounded-lg">✕</button>
          )}
        </div>
        <div className="text-xs text-gray-500 mt-2">
          Slack App → <b>OAuth & Permissions</b> → Bot Token Scopes에 <code className="bg-gray-100 px-1 rounded">chat:write</code>, <code className="bg-gray-100 px-1 rounded">im:write</code> 추가 → <b>Install to Workspace</b> → Bot User OAuth Token (xoxb-...) 복사
        </div>
      </div>

      {/* 작업자 매핑 */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 max-w-3xl mb-4">
        <h2 className="text-base font-bold mb-1">📨 작업자별 DM 라우팅</h2>
        <p className="text-xs text-gray-500 mb-4">
          각 작업자에게 <b>Slack User ID</b>(권장, 봇 이름으로 DM) 또는 <b>Webhook URL</b>(채널용)을 매핑하세요.
          매핑이 없으면 기본 webhook으로 갑니다.
        </p>

        <div className="space-y-2 mb-4">
          {assignees.length === 0 && (
            <div className="text-xs text-gray-400 px-3 py-2 border border-dashed border-gray-200 rounded-lg text-center">
              등록된 작업자 없음 — 아래 + 버튼으로 추가
            </div>
          )}
          {assignees.map((row, idx) => (
            <div key={idx} className="bg-gray-50 border border-gray-200 rounded-lg p-3 space-y-2">
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={row.assignee}
                  onChange={(e) => updateRow(idx, { assignee: e.target.value })}
                  placeholder="담당자 이름"
                  className="flex-1 px-2.5 py-1.5 border border-gray-200 rounded text-sm font-medium"
                  style={{ color: "#e6e9ef" }}
                />
                <button
                  onClick={() => removeRow(idx)}
                  className="px-2 py-1.5 text-xs text-red-600 hover:bg-red-100 rounded"
                  title="행 삭제"
                >
                  ✕
                </button>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs w-14 shrink-0" style={{ color: "#e6e9ef" }}>Email</span>
                <input
                  type="email"
                  value={row.email}
                  onChange={(e) => updateRow(idx, { email: e.target.value })}
                  placeholder="jisu.park@gameberry.co.kr (로그인 이메일 — Hermes 질문 DM 라우팅용)"
                  className="flex-1 px-2.5 py-1.5 border border-gray-200 rounded text-xs bg-white"
                  style={{ color: "#e6e9ef" }}
                />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs w-14 shrink-0" style={{ color: "#e6e9ef" }}>User ID</span>
                <input
                  type="text"
                  value={row.slack_user_id}
                  onChange={(e) => updateRow(idx, { slack_user_id: e.target.value })}
                  placeholder="U01ABC2DEF... (Slack 멤버 ID)"
                  className="flex-1 px-2.5 py-1.5 border border-gray-200 rounded text-xs font-mono bg-white"
                  style={{ color: "#e6e9ef" }}
                />
                <button
                  onClick={() => testRowDM(row, idx)}
                  disabled={testing === `row-${idx}` || !row.slack_user_id}
                  className="px-2.5 py-1.5 text-xs border border-gray-300 rounded hover:bg-white disabled:opacity-40 shrink-0"
                  style={{ color: "#e6e9ef" }}
                  title="Bot DM 테스트"
                >
                  {testing === `row-${idx}` ? "..." : "🤖 DM 테스트"}
                </button>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs w-14 shrink-0 text-gray-400">Webhook</span>
                <input
                  type="password"
                  value={row.webhook_url}
                  onChange={(e) => updateRow(idx, { webhook_url: e.target.value })}
                  placeholder="(선택) https://hooks.slack.com/services/..."
                  className="flex-1 px-2.5 py-1.5 border border-gray-200 rounded text-xs font-mono bg-white"
                  style={{ color: "#e6e9ef" }}
                />
                <button
                  onClick={() => testRowWebhook(row, idx)}
                  disabled={testing === `row-${idx}` || !row.webhook_url || row.webhook_url.startsWith("***")}
                  className="px-2.5 py-1.5 text-xs border border-gray-300 rounded hover:bg-white disabled:opacity-40 shrink-0"
                  style={{ color: "#e6e9ef" }}
                  title="Webhook 테스트"
                >
                  {testing === `row-${idx}` ? "..." : "🪝 Webhook 테스트"}
                </button>
              </div>
            </div>
          ))}
        </div>

        <button
          onClick={addRow}
          className="px-3 py-1.5 text-xs border border-dashed border-gray-300 rounded-lg hover:bg-gray-50"
          style={{ color: "#e6e9ef" }}
        >
          + 작업자 추가
        </button>
      </div>

      {/* 기본 fallback */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 max-w-3xl mb-4">
        <h2 className="text-base font-bold mb-1">🪝 기본 Webhook (fallback)</h2>
        <p className="text-xs text-gray-500 mb-3">
          매핑되지 않은 작업자 또는 담당자 미지정 task용 — 보통 #프로젝트-알림 같은 공용 채널 webhook
        </p>
        <div className="flex items-center gap-2">
          <input
            type="password"
            value={defaultUrl}
            onChange={(e) => setDefaultUrl(e.target.value)}
            placeholder={hasDefault ? `현재: ${maskedDefault}` : "https://hooks.slack.com/services/..."}
            className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm font-mono"
            style={{ color: "#e6e9ef" }}
          />
          <button
            onClick={testDefault}
            disabled={testing === "default" || (!defaultUrl.trim() && !hasDefault)}
            className="px-2.5 py-2 text-xs border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40"
            style={{ color: "#e6e9ef" }}
          >
            {testing === "default" ? "..." : "🚀 테스트"}
          </button>
          {hasDefault && (
            <button onClick={clearDefault} className="px-2.5 py-2 text-xs text-red-600 hover:bg-red-50 rounded-lg">✕</button>
          )}
        </div>
      </div>

      {/* 알림 토글 + 저장 */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 max-w-3xl mb-4">
        <div className="space-y-2 mb-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={notifyCreate} onChange={(e) => setNotifyCreate(e.target.checked)} className="w-4 h-4" />
            <span className="text-sm" style={{ color: "#e6e9ef" }}>새 작업 등록 시 알림</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={notifyStatus} onChange={(e) => setNotifyStatus(e.target.checked)} className="w-4 h-4" />
            <span className="text-sm" style={{ color: "#e6e9ef" }}>작업 상태 변경 시 알림</span>
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={save}
            disabled={saving}
            className="px-4 py-2 text-sm bg-black text-white rounded-lg hover:bg-gray-800 disabled:opacity-40"
          >
            {saving ? "저장 중..." : "전체 저장"}
          </button>
          {notice && <span className="text-sm text-green-600 font-medium">{notice}</span>}
          {error && <span className="text-sm text-red-600">{error}</span>}
        </div>
      </div>

      {/* 가이드 */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 max-w-3xl text-sm" style={{ color: "#e6e9ef" }}>
        <div className="font-bold mb-2">📖 봇이 작업자에게 직접 DM 보내기</div>

        <div className="font-semibold mt-3 mb-1">1단계 — Bot Token 발급 (1번만)</div>
        <ol className="list-decimal list-inside space-y-1 text-xs ml-2">
          <li><a href="https://api.slack.com/apps" target="_blank" rel="noopener" className="text-blue-600 underline">api.slack.com/apps</a> → 만든 앱 클릭</li>
          <li>좌측 <b>Features &gt; OAuth &amp; Permissions</b></li>
          <li><b>Scopes &gt; Bot Token Scopes</b>에 추가:
            <ul className="list-disc list-inside ml-4 mt-0.5">
              <li><code className="bg-white px-1 rounded">chat:write</code></li>
              <li><code className="bg-white px-1 rounded">im:write</code></li>
            </ul>
          </li>
          <li>같은 페이지 상단 <b>Install to Workspace</b> (or <b>Reinstall to Workspace</b>) 클릭 → 권한 승인</li>
          <li>설치 후 <b>Bot User OAuth Token</b>(<code className="bg-white px-1 rounded">xoxb-...</code>)이 표시됨 → 복사 → 위 <b>🤖 Bot Token</b>에 붙여넣기 → 저장</li>
        </ol>

        <div className="font-semibold mt-3 mb-1">2단계 — 작업자 Slack User ID 찾기</div>
        <ol className="list-decimal list-inside space-y-1 text-xs ml-2">
          <li>Slack 앱에서 작업자 이름 클릭 → 프로필 모달 열림</li>
          <li>프로필 우측 상단 <b>⋮ (더보기)</b> → <b>Copy member ID</b></li>
          <li>복사된 ID(<code className="bg-white px-1 rounded">U01ABC2DEF</code> 형식)를 위 작업자 행의 <b>User ID</b>에 붙여넣기</li>
          <li>🤖 DM 테스트 버튼으로 검증</li>
        </ol>

        <div className="font-semibold mt-3 mb-1">동작 우선순위</div>
        <ol className="list-decimal list-inside text-xs ml-2">
          <li>작업자에 <b>User ID</b>가 있고 Bot Token이 있으면 → 봇 이름으로 DM ✓</li>
          <li>없으면 작업자의 <b>Webhook URL</b>로 발송 (DM이면 발신자 = 설치자로 표시됨)</li>
          <li>둘 다 없으면 <b>기본 Webhook</b>으로 발송</li>
        </ol>
      </div>
    </div>
  );
}
