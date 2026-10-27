import type { Metadata } from "next";
import type { ReactNode } from "react";
import { WorkspaceProvider } from "../components/workspace-provider";
import { Shell } from "../components/shell";
import "./globals.css";
export const metadata: Metadata = {
  title: "YAMS · Paper workspace",
  description: "A local workspace for transparent paper market simulations.",
};
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <WorkspaceProvider>
          <Shell>{children}</Shell>
        </WorkspaceProvider>
      </body>
    </html>
  );
}
