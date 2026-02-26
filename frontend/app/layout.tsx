import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "문서 아카이브",
  description: "OpenClaw + Telegram 기반 문서 아카이브",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
