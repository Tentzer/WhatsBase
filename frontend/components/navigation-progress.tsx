"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

interface NavProgressCtx {
  navigate: (href: string) => void;
}

const NavProgressContext = createContext<NavProgressCtx>({
  navigate: () => {},
});

export function useNavigate() {
  return useContext(NavProgressContext).navigate;
}

export function NavigationProgressProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const prevPathname = useRef(pathname);
  const [spinning, setSpinning] = useState(false);

  // Clear spinner as soon as the new page is rendered
  useEffect(() => {
    if (pathname !== prevPathname.current) {
      prevPathname.current = pathname;
      setSpinning(false);
    }
  }, [pathname]);

  const navigate = useCallback(
    (href: string) => {
      setSpinning(true);
      router.push(href);
    },
    [router],
  );

  return (
    <NavProgressContext.Provider value={{ navigate }}>
      {children}
      {spinning && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center">
          {/* Blurred backdrop */}
          <div className="absolute inset-0 bg-background/60 backdrop-blur-sm" />
          {/* Spinner */}
          <div className="relative flex h-20 w-20 items-center justify-center rounded-2xl bg-emerald-600 shadow-2xl shadow-emerald-500/40 ring-1 ring-white/10">
            <svg
              className="size-10 animate-spin text-white"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-80"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
          </div>
        </div>
      )}
    </NavProgressContext.Provider>
  );
}
