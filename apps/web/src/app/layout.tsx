import type { Metadata } from "next";
import "./globals.css";

import AuthProvider from "@/components/AuthProvider";

export const metadata: Metadata = {
  title: "AllerNav — Agentic AI Dining Safety Assistant",
  description:
    "Evidence-backed dining decision support that surfaces allergen risks, missing information, and recommended questions for restaurant staff.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body><AuthProvider>{children}</AuthProvider></body>
    </html>
  );
}
