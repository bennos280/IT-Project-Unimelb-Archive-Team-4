import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";

import { describe, fieldsOf, ruleTypes, type Rule, type RuleType, type Rules, type Template } from "./rules";

// Each of the template's fields with its rule: its type, whether it's required, the values or range it may take, and its
// description, which the model reads (it's the field's value in the template).
export default function FieldRules({ template, rules, onRules, onTemplate }: {
  template: Template; rules: Rules; onRules: (rules: Rules) => void; onTemplate: (text: string) => void;
}) {
  const set = (path: string, change: Partial<Rule>) => onRules({ ...rules, [path]: { ...(rules[path] ?? { type: "text" }), ...change } });
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Field</TableHead>
          <TableHead className="w-40">Type</TableHead>
          <TableHead className="w-20">Required</TableHead>
          <TableHead className="w-56">Allowed</TableHead>
          <TableHead>Description</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {fieldsOf(template).map(([path, description]) => {
          const rule = rules[path] ?? { type: "text" };
          return (
            <TableRow key={path}>
              <TableCell className="font-mono text-xs whitespace-normal [overflow-wrap:anywhere]">{path}</TableCell>
              <TableCell>
                <NativeSelect aria-label={`${path} type`} className="w-full" value={rule.type}
                  onChange={(e) => set(path, { type: e.target.value as RuleType })}>
                  {Object.entries(ruleTypes).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
                </NativeSelect>
              </TableCell>
              <TableCell>
                <input type="checkbox" aria-label={`${path} required`} className="size-4 accent-primary" checked={Boolean(rule.required)}
                  onChange={(e) => set(path, { required: e.target.checked })} />
              </TableCell>
              <TableCell className="whitespace-normal">
                {(rule.type === "number" || rule.type === "date") && (
                  <div className="flex gap-1">
                    <Input aria-label={`${path} from`} placeholder={rule.type === "number" ? "From" : "From, e.g. 1914"} value={rule.min ?? ""}
                      onChange={(e) => set(path, { min: e.target.value })} />
                    <Input aria-label={`${path} to`} placeholder={rule.type === "number" ? "To" : "To, e.g. 1920"} value={rule.max ?? ""}
                      onChange={(e) => set(path, { max: e.target.value })} />
                  </div>
                )}
                {(rule.type === "one_of" || rule.type === "several_of") && (
                  <Textarea aria-label={`${path} values`} rows={2} className="min-h-0 text-xs" placeholder={"One a line, e.g.\nPOW = Prisoner of war"}
                    value={(rule.values ?? []).join("\n")} onChange={(e) => set(path, { values: e.target.value.split("\n") })} />
                )}
                {rule.type === "pattern" && (
                  <div className="flex flex-col gap-1">
                    <Input aria-label={`${path} pattern`} className="font-mono text-xs" placeholder="e.g. [A-Z]?\d+" value={rule.pattern ?? ""}
                      onChange={(e) => set(path, { pattern: e.target.value })} />
                    <Input aria-label={`${path} example`} placeholder="An example, e.g. A12524" value={rule.example ?? ""}
                      onChange={(e) => set(path, { example: e.target.value })} />
                  </div>
                )}
                {rule.type === "text" && <span className="text-muted-foreground">Any</span>}
                {rule.type === "yes_no" && <span className="text-muted-foreground">Yes or no, Y or N, ✓ or ✗</span>}
              </TableCell>
              <TableCell>
                <Input aria-label={`${path} description`} placeholder="What it holds" value={description ?? ""}
                  onChange={(e) => onTemplate(describe(template, path, e.target.value))} />
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
