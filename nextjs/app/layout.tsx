import type { Metadata, Viewport } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Wine Shelf Scanner',
  description: 'Take a photo of any wine shelf and instantly see ratings overlaid on each bottle',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-sans bg-app-bg min-h-screen">
        {children}
      </body>
    </html>
  );
}
