import { useEffect, useState } from "react";

import CollectionsScreen from "./collections/CollectionsScreen";
import ImportScreen from "./import/ImportScreen";
import ReviewScreen from "./review-screen/ReviewScreen";
import { useReviewSession } from "./review-screen/useReviewSession";
import ProgressDashboard from "./progress/ProgressDashboard";
import PageTypesScreen from "./settings/PageTypesScreen";
import SettingsScreen from "./settings/SettingsScreen";
import { keepPerson, storedPerson } from "./person";
import { getReviewers } from "./review-screen/api";
import { itemParam, seriesParam } from "./progress/backend";

// Mount the review session only on survey URLs, avoiding API calls on the dashboard.
function SurveyReview() {
  const session = useReviewSession();
  return <ReviewScreen session={session}/>;
}
// Home lists the series; /?series=<id> is one series' items. Until this browser knows who is working, any page is
// home, whose welcome asks, then the page asked for; asked again if the name kept isn't one of this database's (another's).
export default function App() {
  const [person, setPerson] = useState(storedPerson);
  useEffect(() => {
    if (!person) return;
    getReviewers().then((people) => {
      if (people.some((p) => p.id === person.id && p.name === person.name)) return;
      keepPerson(null);
      setPerson(null);
    }).catch(() => {});
  }, [person]);
  if (!person) return <CollectionsScreen onChosen={setPerson} />;
  const params = new URLSearchParams(location.search);
  const view = params.get("view");
  if (view === "import") return <ImportScreen/>;
  if (view === "settings") return <SettingsScreen/>;
  if ((view === "setup" || view === "page-types") && !seriesParam(params)) return <CollectionsScreen/>; // which series's? home asks
  if (view === "setup" || view === "page-types") return <PageTypesScreen/>; // page-types: the old name of a series' Setup
  if (params.has("survey")) return <SurveyReview/>;
  return seriesParam(params) || itemParam(params) ? <ProgressDashboard/> : <CollectionsScreen/>; // an item alone: series 1
}
