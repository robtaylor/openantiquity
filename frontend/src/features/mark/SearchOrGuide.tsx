import { useEffect, useState } from "react";
import { SearchBox, type SearchDone } from "../search/SearchBox.js";
import { DrawingGuide } from "./DrawingGuide.js";
import { useMarkingOpen } from "./MarkLayer.js";

/**
 * What sits at the top left of the map: the search box, or while the
 * drawing tool is open the drawing guide in its place. The guide's search
 * button brings the search box back, with focus in it, until a result is
 * chosen, Escape is pressed in the empty box, or the empty box loses focus.
 */
export function SearchOrGuide() {
  const drawing = useMarkingOpen();
  const [searching, setSearching] = useState(false);
  const [back, setBack] = useState<SearchDone | null>(null);

  // Each time the tool opens, it opens with the guide.
  useEffect(() => {
    if (!drawing) {
      setSearching(false);
      setBack(null);
    }
  }, [drawing]);

  if (!drawing) return <SearchBox />;
  if (!searching) {
    return (
      <DrawingGuide
        onSearch={() => {
          setBack(null);
          setSearching(true);
        }}
        focusSearch={back === "escape"}
      />
    );
  }
  return (
    <SearchBox
      autoFocus
      onDone={(how) => {
        setBack(how);
        setSearching(false);
      }}
    />
  );
}
