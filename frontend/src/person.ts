import type { Reviewer } from "./review-screen/api";

const KEY = "prestcribe.person";
let chosen: Reviewer | null = null; // kept here too, for a browser that keeps nothing

// Who is working in this browser: chosen on the name screen and recorded with everything they save. Kept in this browser until
// switched; a convenience, not a login. null until chosen.
export function storedPerson(): Reviewer | null {
  try {
    const found = JSON.parse(localStorage.getItem(KEY) ?? "null");
    return found && typeof found.id === "number" && typeof found.name === "string" ? { id: found.id, name: found.name } : chosen;
  } catch {
    return chosen;
  }
}

export function keepPerson(person: Reviewer | null) {
  chosen = person;
  try {
    if (person) localStorage.setItem(KEY, JSON.stringify(person));
    else localStorage.removeItem(KEY);
  } catch {
    // not kept: asked again next time
  }
}

// The person working; the app shows the name screen until there is one (App), so a screen can count on it.
export const me = () => storedPerson()!;
