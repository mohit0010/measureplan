import React from "react";
import { Link, useLocation } from "react-router-dom";
import { Moon, Sun, Ruler, History as HistoryIcon } from "lucide-react";
import { useTheme } from "../lib/theme";
import { HOME } from "../constants/testIds";

const Nav = () => {
  const { theme, toggle } = useTheme();
  const loc = useLocation();

  const NavLink = ({ to, children, testid }) => {
    const active = loc.pathname === to;
    return (
      <Link
        to={to}
        data-testid={testid}
        className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
          active
            ? "bg-secondary text-foreground"
            : "text-muted-foreground hover:text-foreground hover:bg-secondary/60"
        }`}
      >
        {children}
      </Link>
    );
  };

  return (
    <header className="sticky top-0 z-40 glass">
      <div className="max-w-[1440px] mx-auto flex items-center justify-between px-6 py-3">
        <Link to="/" className="flex items-center gap-2.5 group">
          <span className="w-8 h-8 rounded-md bg-primary text-primary-foreground grid place-items-center shadow-sm">
            <Ruler className="w-4 h-4" strokeWidth={2.5} />
          </span>
          <div className="leading-tight">
            <div className="font-display text-[15px] font-bold tracking-tight">
              PlanMeasure <span className="text-primary">AI</span>
            </div>
            <div className="overline text-[9px] mt-[1px]">
              v1 · Floor Plan Intelligence
            </div>
          </div>
        </Link>

        <nav className="flex items-center gap-1">
          <NavLink to="/" testid={HOME.navHome}>Home</NavLink>
          <NavLink to="/history" testid={HOME.navHistory}>
            <span className="inline-flex items-center gap-1.5">
              <HistoryIcon className="w-3.5 h-3.5" /> History
            </span>
          </NavLink>
          <button
            data-testid={HOME.themeToggle}
            onClick={toggle}
            aria-label="Toggle theme"
            className="ml-2 w-9 h-9 rounded-md border border-border grid place-items-center hover:bg-secondary transition-colors"
          >
            {theme === "dark" ? (
              <Sun className="w-4 h-4" />
            ) : (
              <Moon className="w-4 h-4" />
            )}
          </button>
        </nav>
      </div>
    </header>
  );
};

export default Nav;
