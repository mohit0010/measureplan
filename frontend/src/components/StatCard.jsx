import React from "react";
import { Card } from "./ui/card";

const StatCard = ({
  label,
  value,
  unit,
  sub,
  accent = "primary",
  testid,
  icon: Icon,
}) => {
  return (
    <Card
      data-testid={testid}
      className="relative overflow-hidden p-5 rounded-md border border-border shadow-sm hover:shadow-md transition-shadow group"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="overline">{label}</div>
        {Icon && (
          <div className={`w-8 h-8 rounded-md grid place-items-center bg-${accent}/10`}>
            <Icon className={`w-4 h-4 text-${accent}`} strokeWidth={2} />
          </div>
        )}
      </div>
      <div className="mt-3 flex items-baseline gap-1.5">
        <div className="stat-num text-3xl md:text-4xl font-semibold text-foreground">
          {value}
        </div>
        {unit && (
          <div className="text-sm text-muted-foreground font-mono-plex">
            {unit}
          </div>
        )}
      </div>
      {sub && (
        <div className="mt-1.5 text-xs text-muted-foreground font-mono-plex">
          {sub}
        </div>
      )}
      <div className="absolute inset-x-0 bottom-0 h-[2px] bg-gradient-to-r from-transparent via-primary/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
    </Card>
  );
};

export default StatCard;
