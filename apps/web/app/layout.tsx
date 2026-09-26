import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Tandem",
  description: "Transmission projects under 25 miles apart, ranked by time gap.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
