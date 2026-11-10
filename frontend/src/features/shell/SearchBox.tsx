import { Search } from "lucide-react";
import { type FormEvent, useId, useState } from "react";
import { toast } from "../../ui/toastStore.js";

/**
 * The search field. It is an input only for now: results arrive with the
 * search feature, which will ask `GET /geo/search` for places, grid
 * references, records and findings. Until then a search says so, because
 * every action owes its user an answer.
 */
export function SearchBox() {
  const [query, setQuery] = useState("");
  const id = useId();

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (query.trim() === "") return;
    toast("Search isn't built yet. For now, drag and zoom the map to where you want to look.");
  }

  return (
    <search className="fc-search">
      <form onSubmit={onSubmit}>
        <label className="fc-visually-hidden" htmlFor={id}>
          Search for a place, grid reference or record
        </label>
        <Search className="fc-search__icon" size={18} aria-hidden />
        <input
          id={id}
          className="fc-search__input"
          type="search"
          name="q"
          value={query}
          placeholder="Search a place or grid reference"
          autoComplete="off"
          spellCheck={false}
          enterKeyHint="search"
          onChange={(event) => setQuery(event.currentTarget.value)}
        />
      </form>
    </search>
  );
}
