import { useEffect, useState } from "react";

import CollectionsScreen from "./collections/CollectionsScreen";
import ImportScreen from "./import/ImportScreen";
import ReviewScreen from "./review-screen/ReviewScreen";
import { useReviewSession } from "./review-screen/useReviewSession";
import ProgressDashboard from "./progress/ProgressDashboard";
import LevelScreen from "./settings/LevelScreen";
import PageTypesScreen from "./settings/PageTypesScreen";
import SettingsScreen from "./settings/SettingsScreen";
import TasksScreen, { TaskScreen } from "./tasks/TasksScreen";
import { keepPerson, storedPerson } from "./person";
import { getReviewers } from "./review-screen/api";

// Mount the review session only on survey URLs, avoiding API calls on the dashboard.
function SurveyReview() {
  const session = useReviewSession();
  return <ReviewScreen session={session}/>;
}
// Home lists the collections; /?collection=<id> is one collection's bundles. Until this browser knows who is working, any page is
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
  if (view === "tasks") return params.get("task") ? <TaskScreen id={params.get("task")!}/> : <TasksScreen/>;
  if ((view === "setup" || view === "page-types") && !params.get("collection")) return <CollectionsScreen/>; // which series's? home asks
  if (view === "setup" && params.has("level")) return <LevelScreen/>; // one of the series' levels of record
  if (view === "setup" || view === "page-types") return <PageTypesScreen/>; // page-types: the old name of a series' Setup
  if (params.has("survey")) return <SurveyReview/>;
  return params.has("collection") || params.has("bundle") ? <ProgressDashboard/> : <CollectionsScreen/>; // an old /?bundle= link: collection 1
}
