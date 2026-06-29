import * as React from "react";

// 흑백 라인 아이콘셋 (stroke=currentColor → 다크/라이트 자동, emoji 대체)
const PATHS: Record<string, React.ReactNode> = {
  home: (<><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V21h14V9.5" /></>),
  tasks: (<><rect x="6" y="4" width="12" height="17" rx="2" /><path d="M9 3h6v3H9z" /><path d="M8.5 12.5l2 2 4-4.5" /></>),
  mic: (<><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M6 11a6 6 0 0 0 12 0" /><path d="M12 17v4" /><path d="M9 21h6" /></>),
  balloon: (<><ellipse cx="12" cy="9" rx="6" ry="7" /><path d="M12 16v3" /><path d="M11 19h2" /></>),
  cpu: (<><rect x="6" y="6" width="12" height="12" rx="2" /><rect x="9.5" y="9.5" width="5" height="5" /><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3" /></>),
  image: (<><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="8.5" cy="9.5" r="1.5" /><path d="M21 16l-5-5L5 20" /></>),
  map: (<><path d="M9 4 3 6.5v13L9 17l6 2.5 6-2.5v-13L15 6.5 9 4z" /><path d="M9 4v13M15 6.5v13" /></>),
  palette: (<><path d="M12 3a9 9 0 1 0 0 18c.9 0 1.4-.8 1.4-1.5 0-1 .8-1.5 1.6-1.5H17A3 3 0 0 0 20 15a9 9 0 0 0-8-12z" /><circle cx="7.5" cy="10.5" r=".9" fill="currentColor" stroke="none" /><circle cx="12" cy="7.5" r=".9" fill="currentColor" stroke="none" /><circle cx="16" cy="10.5" r=".9" fill="currentColor" stroke="none" /></>),
  gear: (<><circle cx="12" cy="12" r="3.2" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1" /></>),
  more: (<><circle cx="6" cy="12" r="1.5" fill="currentColor" stroke="none" /><circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" /><circle cx="18" cy="12" r="1.5" fill="currentColor" stroke="none" /></>),
  graph: (<><circle cx="6" cy="6.5" r="2.2" /><circle cx="18" cy="8" r="2.2" /><circle cx="10.5" cy="18" r="2.2" /><path d="M8 7l7.8 1M9.6 16 7 8.5M16.3 9.7 12 16.2" /></>),
  zap: (<><path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" /></>),
  flask: (<><path d="M9 3h6M10 3v6l-5.2 9.2A2 2 0 0 0 6.5 21h11a2 2 0 0 0 1.7-2.8L14 9V3" /><path d="M7.5 14h9" /></>),
  music: (<><path d="M9 18V5l10-2v13" /><circle cx="6" cy="18" r="3" /><circle cx="16" cy="16" r="3" /></>),
  search: (<><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></>),
  target: (<><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3.2" /><path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3" /></>),
  edit: (<><path d="M4 20h4L18.6 9.4a2.1 2.1 0 0 0-3-3L5 17v3z" /><path d="M13.5 6.5l3 3" /></>),
  ban: (<><circle cx="12" cy="12" r="9" /><path d="M5.6 5.6l12.8 12.8" /></>),
  help: (<><circle cx="12" cy="12" r="9" /><path d="M9.3 9a3 3 0 0 1 5.5 1c0 2-3 2.4-3 4" /><circle cx="11.8" cy="17" r=".7" fill="currentColor" stroke="none" /></>),
  paperclip: (<><path d="M21 10.5 12 19.4a5 5 0 0 1-7-7l9-9a3.3 3.3 0 0 1 4.7 4.7l-9 9a1.7 1.7 0 0 1-2.4-2.4l8.1-8.1" /></>),
  x: (<><path d="M6 6l12 12M18 6 6 18" /></>),
  play: (<><path d="M7 5l12 7-12 7z" /></>),
  check: (<><path d="M4 12.5l5 5 11-11" /></>),
  code: (<><path d="M9 7l-5 5 5 5M15 7l5 5-5 5" /></>),
  brain: (<><path d="M12 5a3.5 3.5 0 0 0-3.5 3.5c-1.8.4-2.6 3.2-.4 4.6-.4 2 1.2 3.9 3 3.9h.9V5z" /><path d="M12 5a3.5 3.5 0 0 1 3.5 3.5c1.8.4 2.6 3.2.4 4.6.4 2-1.2 3.9-3 3.9H12" /></>),
  users: (<><circle cx="8" cy="9" r="3" /><circle cx="16.5" cy="9.5" r="2.5" /><path d="M3 19c0-2.8 2.2-4.5 5-4.5s5 1.7 5 4.5M14 19c0-2.4 1.8-3.8 4-3.8" /></>),
  eye: (<><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>),
  ruler: (<><path d="M4 16 16 4l4 4L8 20z" /><path d="M9 9l1.5 1.5M12 6l1.5 1.5M6 12l1.5 1.5" /></>),
  scale: (<><path d="M12 4v16M7 20h10M3 9h18" /><path d="M6 9l-2.2 4.5h4.4zM18 9l-2.2 4.5h4.4z" /></>),
  doc: (<><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4M9 12h6M9 16h6" /></>),
  bot: (<><rect x="5" y="8" width="14" height="10" rx="2" /><circle cx="9.5" cy="13" r="1" fill="currentColor" stroke="none" /><circle cx="14.5" cy="13" r="1" fill="currentColor" stroke="none" /><path d="M12 5v3" /><circle cx="12" cy="4" r="1" /></>),
  dollar: (<><path d="M12 2v20M16 6.5C16 4.6 14.2 3.5 12 3.5S8 4.6 8 6.5s2 2.5 4 3 4 1 4 3.5-1.8 3.5-4 3.5-4-1-4-3" /></>),
  flag: (<><path d="M5 21V4M5 4h11l-2 3 2 3H5" /></>),
  box: (<><path d="M3 7.5 12 3l9 4.5v9L12 21 3 16.5z" /><path d="M3 7.5 12 12l9-4.5M12 12v9" /></>),
  rocket: (<><path d="M5.5 14.5c-1 1-1.2 4.2-1.2 4.2s3.2-.2 4.2-1.2m-3-3a9 9 0 0 1 13-8.5 9 9 0 0 1-8.5 13l-2.2-.9-1.3-1.3z" /><circle cx="14.5" cy="9.5" r="1.6" /></>),
  signal: (<><path d="M3 12h4l3 8 4-16 3 8h4" /></>),
  award: (<><circle cx="12" cy="9" r="5" /><path d="M9 13.2 8 21l4-2.2 4 2.2-1-7.8" /></>),
  dna: (<><path d="M7 4c0 6 10 10 10 16M17 4c0 6-10 10-10 16M8.5 7h7M8.5 17h7M10.5 10h3M10.5 14h3" /></>),
  calendar: (<><rect x="4" y="5" width="16" height="16" rx="2" /><path d="M4 9h16M8 3v4M16 3v4" /></>),
  star: (<><path d="M12 3l2.6 5.6 6 .8-4.4 4.2 1.1 6.1-5.3-3-5.3 3 1.1-6.1L3.4 9.4l6-.8z" /></>),
  chat: (<><path d="M4 5h16v11H8l-4 4z" /></>),
  clock: (<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>),
  wrench: (<><path d="M14.5 6a3.8 3.8 0 0 0-5 4.8L4 16.3 7.7 20l5.5-5.5A3.8 3.8 0 0 0 18 9.5l-2.6 2.6-2-2L16 7.5A3.8 3.8 0 0 0 14.5 6z" /></>),
  undo: (<><path d="M4 9h11a5 5 0 0 1 0 10h-3M4 9l4-4M4 9l4 4" /></>),
  arrowup: (<><path d="M12 19V5M6 11l6-6 6 6" /></>),
  dot: (<><circle cx="12" cy="12" r="5" fill="currentColor" stroke="none" /></>),
  plus: (<><path d="M12 5v14M5 12h14" /></>),
  bell: (<><path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6z" /><path d="M10 20a2 2 0 0 0 4 0" /></>),
  menu: (<><path d="M4 6h16M4 12h16M4 18h16" /></>),
  folder: (<><path d="M3 6h6l2 2h10v11H3z" /></>),
};

export default function Icon({ name, size = 22, className }: { name: string; size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      {PATHS[name] || PATHS.more}
    </svg>
  );
}
