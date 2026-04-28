import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ASU Museum — Carmen Lomas Garza",
  description:
    "A conversational mobile tour of the Carmen Lomas Garza exhibition at the ASU Museum.",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    title: "ASU Museum",
    statusBarStyle: "black-translucent",
  },
};

export const viewport: Viewport = {
  themeColor: "#F4ECE0",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-sans">{children}</body>
    </html>
  );
}
