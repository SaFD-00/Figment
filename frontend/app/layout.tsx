import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Figment — AI figures & images, made effortless",
  description:
    "Figment turns ideas into editable scientific figures and images. Generate from text, sketches, or references; edit in-canvas; export to PPTX, SVG, or PNG.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        {/* Inter (figurelabs-style); degrades to system sans if offline. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
