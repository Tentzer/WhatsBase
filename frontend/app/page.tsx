import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";

export default function Home() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <main className="w-full max-w-3xl rounded-2xl border bg-card p-8 shadow-sm sm:p-12">
        <p className="text-sm font-medium text-emerald-700">WhatsBase</p>
        <h1 className="mt-2 text-4xl font-semibold tracking-tight text-foreground">
          Build a WhatsApp sales agent in minutes
        </h1>
        <p className="mt-4 text-lg text-muted-foreground">
          Upload your catalog, connect your WhatsApp number, and launch a tenant-ready AI sales
          assistant with Hebrew and English support.
        </p>
        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <Link
            href="/signup"
            className={buttonVariants({ className: "bg-emerald-600 hover:bg-emerald-700" })}
          >
            Get started
          </Link>
          <Link href="/login" className={buttonVariants({ variant: "outline" })}>
            I already have an account
          </Link>
        </div>
        <p className="mt-6 text-sm text-muted-foreground">
          Demo mode is enabled: onboarding, build simulation, and test chat work without backend
          API wiring.
        </p>
      </main>
    </div>
  );
}
