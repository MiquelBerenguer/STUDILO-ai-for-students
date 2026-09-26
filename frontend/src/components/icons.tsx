// Icon set from the reference design (design/reference/src/App.tsx), plus a few for new interactions.
import type { ReactNode } from "react";

export type IconName =
  | "spark" | "home" | "calendar" | "book" | "exam" | "chart" | "settings" | "bell" | "arrow" | "clock"
  | "check" | "send" | "plus" | "upload" | "undo" | "x" | "camera" | "link" | "text" | "alert" | "chevron";

const paths: Record<IconName, ReactNode> = {
  spark: <path d="m12 2 1.2 5.1L18 9l-4.8 1.9L12 16l-1.2-5.1L6 9l4.8-1.9L12 2ZM5 15l.7 2.3L8 18l-2.3.7L5 21l-.7-2.3L2 18l2.3-.7L5 15Zm14-2 .7 2.3 2.3.7-2.3.7L19 19l-.7-2.3L16 16l2.3-.7L19 13Z" />,
  home: <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1V10Z" />,
  calendar: <><path d="M4 5h16v16H4zM8 3v4m8-4v4M4 10h16" /><path d="M8 14h2m4 0h2m-8 4h2" /></>,
  book: <path d="M4 4h7a3 3 0 0 1 3 3v14a3 3 0 0 0-3-3H4V4Zm16 0h-3a3 3 0 0 0-3 3v14a3 3 0 0 1 3-3h3V4Z" />,
  exam: <><path d="M7 3h10v4h3v14H4V7h3V3Z" /><path d="M8 12h8m-8 4h5" /></>,
  chart: <path d="M4 20V10m6 10V4m6 16v-7m5 7H2" />,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></>,
  arrow: <path d="m9 18 6-6-6-6" />,
  chevron: <path d="m6 9 6 6 6-6" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  send: <path d="m22 2-7 20-4-9-9-4 20-7ZM11 13 22 2" />,
  plus: <path d="M12 5v14m-7-7h14" />,
  upload: <><path d="M12 16V4m-5 5 5-5 5 5" /><path d="M5 15v5h14v-5" /></>,
  undo: <><path d="M9 14 4 9l5-5" /><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11" /></>,
  x: <path d="M6 6l12 12M18 6 6 18" />,
  camera: <><path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" /></>,
  link: <><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></>,
  text: <path d="M4 6h16M4 12h16M4 18h10" />,
  alert: <><path d="M12 3 2 21h20L12 3Z" /><path d="M12 10v5m0 3v.5" /></>,
};

export function Icon({ name, className = "", solid = false }: { name: IconName; className?: string; solid?: boolean }) {
  return (
    <svg className={`icon ${solid ? "solid" : ""} ${className}`} viewBox="0 0 24 24" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}

export function BrandMark({ size = "h-9 w-9" }: { size?: string }) {
  return (
    <span className={`brand-mark ${size}`}>
      <Icon name="spark" solid className="h-[58%] w-[58%]" />
    </span>
  );
}
