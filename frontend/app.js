const API_BASE = window.location.origin;
const currentUserId = "default";
const PROJECT_COLORS_KEY = "planpal-project-colors";
const DEFAULT_PROJECT_COLOR = "#004ac6";
const NO_TIME_VALUE = "__no_time__";
const ALL_DAY_DURATION_VALUE = "all_day";

let tasks = [];
let pendingTask = null;
let activeView = "calendar";
let entryMode = "auto";
let pendingEntryMode = "auto";
let calendarCursor = new Date();
let calendarMode = window.matchMedia?.("(max-width: 760px)")?.matches ? "schedule" : "month";
let selectedCalendarDate = localDateKey(new Date());
let projectColors = loadProjectColors();
let deferredInstallPrompt = null;

const elements = {
  taskInput: document.querySelector("#task-input"),
  parseButton: document.querySelector("#parse-button"),
  parseButtonLabel: document.querySelector("#parse-button-label"),
  autoModeButton: document.querySelector("#auto-mode-button"),
  manualModeButton: document.querySelector("#manual-mode-button"),
  reviewPanel: document.querySelector("#review-panel"),
  titleInput: document.querySelector("#parsed-title-input"),
  descriptionInput: document.querySelector("#parsed-description-input"),
  dateInput: document.querySelector("#parsed-date-input"),
  timeInput: document.querySelector("#parsed-time-input"),
  durationInput: document.querySelector("#parsed-duration-input"),
  durationSlider: document.querySelector("#duration-slider-input"),
  timePickerReadout: document.querySelector("#time-picker-readout"),
  durationPickerReadout: document.querySelector("#duration-picker-readout"),
  projectInput: document.querySelector("#parsed-project-input"),
  newProjectInput: document.querySelector("#new-project-input"),
  projectColorInput: document.querySelector("#project-color-input"),
  missingInfo: document.querySelector("#parsed-missing-info"),
  followUpSection: document.querySelector("#follow-up-section"),
  followUpFields: document.querySelector("#follow-up-fields"),
  followUpOpenText: document.querySelector("#follow-up-open-text"),
  applyDetailsButton: document.querySelector("#apply-details-button"),
  confirmButton: document.querySelector("#confirm-button"),
  discardButton: document.querySelector("#discard-button"),
  loadingOverlay: document.querySelector("#loading-overlay"),
  loadingMessage: document.querySelector("#loading-message"),
  errorArea: document.querySelector("#error-area"),
  errorMessage: document.querySelector("#error-message"),
  toastRegion: document.querySelector("#toast-region"),
  installAppButton: document.querySelector("#install-app-button"),
  mobileInstallButton: document.querySelector("#mobile-install-button"),
  syncButton: document.querySelector("#sync-button"),
  mobileSyncButton: document.querySelector("#mobile-sync-button"),
  mobileMenuButton: document.querySelector("#mobile-menu-button"),
  mobileMenu: document.querySelector("#mobile-menu"),
  calendarMonthLabel: document.querySelector("#calendar-month-label"),
  calendarPrevButton: document.querySelector("#calendar-prev-button"),
  calendarNextButton: document.querySelector("#calendar-next-button"),
  calendarTodayButton: document.querySelector("#calendar-today-button"),
  calendarMonthModeButton: document.querySelector("#calendar-month-mode-button"),
  calendarWeekModeButton: document.querySelector("#calendar-week-mode-button"),
  calendarScheduleModeButton: document.querySelector("#calendar-schedule-mode-button"),
  calendarSelectedDate: document.querySelector("#calendar-selected-date"),
  calendarSelectedSummary: document.querySelector("#calendar-selected-summary"),
  calendarSelectedList: document.querySelector("#calendar-selected-list"),
};

const listElements = {
  tasks: document.querySelector("#tasks-list"),
  events: document.querySelector("#events-list"),
  calendar: document.querySelector("#calendar-list"),
  calendarWeekDayScroller: document.querySelector("#calendar-week-day-scroller"),
  calendarWeekAgenda: document.querySelector("#calendar-week-agenda"),
  calendarSchedule: document.querySelector("#calendar-schedule-list"),
  projects: document.querySelector("#projects-list"),
  archive: document.querySelector("#archive-list"),
};

const emptyElements = {
  tasks: document.querySelector("#tasks-empty"),
  events: document.querySelector("#events-empty"),
  calendar: document.querySelector("#calendar-empty"),
  projects: document.querySelector("#projects-empty"),
  archive: document.querySelector("#archive-empty"),
};

document.addEventListener("DOMContentLoaded", () => {
  initializeTimeOptions();
  bindEvents();
  setupInstallPrompt();
  loadTasks({ quiet: true });
  registerServiceWorker();
});

function bindEvents() {
  elements.parseButton.addEventListener("click", handleParse);
  elements.autoModeButton.addEventListener("click", () => setEntryMode("auto"));
  elements.manualModeButton.addEventListener("click", () => setEntryMode("manual"));
  elements.applyDetailsButton.addEventListener("click", handleApplyDetails);
  elements.confirmButton.addEventListener("click", handleConfirm);
  elements.discardButton.addEventListener("click", resetPendingTask);
  elements.timeInput.addEventListener("change", updateDurationOptionsForTime);
  elements.durationInput.addEventListener("change", () => {
    if (elements.durationInput.value === ALL_DAY_DURATION_VALUE) {
      elements.timeInput.value = NO_TIME_VALUE;
      updateDurationOptionsForTime();
    }
    renderReviewPickers();
  });
  elements.reviewPanel.addEventListener("click", handleReviewPickerClick);
  elements.durationSlider?.addEventListener("input", () => {
    setDurationValue(elements.durationSlider.value);
  });
  elements.newProjectInput.addEventListener("input", () => {
    if (elements.newProjectInput.value.trim()) {
      elements.projectInput.value = "";
    }
    syncProjectColorInput();
  });
  elements.projectInput.addEventListener("change", syncProjectColorInput);
  elements.installAppButton?.addEventListener("click", handleInstallApp);
  elements.mobileInstallButton?.addEventListener("click", handleInstallApp);
  elements.syncButton?.addEventListener("click", () => loadTasks());
  elements.mobileSyncButton?.addEventListener("click", () => loadTasks());
  elements.mobileMenuButton?.addEventListener("click", toggleMobileMenu);
  elements.calendarPrevButton?.addEventListener("click", () => shiftCalendarMonth(-1));
  elements.calendarNextButton?.addEventListener("click", () => shiftCalendarMonth(1));
  elements.calendarTodayButton?.addEventListener("click", () => {
    calendarCursor = new Date();
    selectedCalendarDate = localDateKey(new Date());
    renderTasks();
  });
  elements.calendarMonthModeButton?.addEventListener("click", () => setCalendarMode("month"));
  elements.calendarWeekModeButton?.addEventListener("click", () => setCalendarMode("week"));
  elements.calendarScheduleModeButton?.addEventListener("click", () => setCalendarMode("schedule"));

  elements.taskInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      handleParse();
    }
  });

  document.querySelectorAll("[data-view]").forEach((trigger) => {
    trigger.addEventListener("click", () => switchView(trigger.dataset.view));
  });

  document.addEventListener("click", (event) => {
    if (!elements.mobileMenu || !elements.mobileMenuButton || isMobileMenuClosed()) return;
    if (elements.mobileMenu.contains(event.target) || elements.mobileMenuButton.contains(event.target)) return;
    closeMobileMenu();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMobileMenu();
  });

  window.matchMedia?.("(min-width: 1024px)")?.addEventListener?.("change", closeMobileMenu);
}

function toggleMobileMenu() {
  if (isMobileMenuClosed()) {
    openMobileMenu();
  } else {
    closeMobileMenu();
  }
}

function openMobileMenu() {
  elements.mobileMenu?.classList.remove("hidden");
  elements.mobileMenu?.classList.add("flex");
  elements.mobileMenuButton?.setAttribute("aria-expanded", "true");
  elements.mobileMenuButton?.setAttribute("aria-label", "Close menu");
}

function closeMobileMenu() {
  elements.mobileMenu?.classList.add("hidden");
  elements.mobileMenu?.classList.remove("flex");
  elements.mobileMenuButton?.setAttribute("aria-expanded", "false");
  elements.mobileMenuButton?.setAttribute("aria-label", "Open menu");
}

function isMobileMenuClosed() {
  return !elements.mobileMenu || elements.mobileMenu.classList.contains("hidden");
}

function setupInstallPrompt() {
  updateInstallAvailability();

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredInstallPrompt = event;
    updateInstallAvailability();
  });

  window.addEventListener("appinstalled", () => {
    deferredInstallPrompt = null;
    updateInstallAvailability();
    showToast("PlanPal installed");
  });

  const standaloneQuery = window.matchMedia?.("(display-mode: standalone)");
  standaloneQuery?.addEventListener?.("change", updateInstallAvailability);
}

async function handleInstallApp() {
  if (!deferredInstallPrompt) {
    showInstallHelp();
    return;
  }

  deferredInstallPrompt.prompt();
  const choice = await deferredInstallPrompt.userChoice.catch(() => null);
  deferredInstallPrompt = null;
  updateInstallAvailability();

  if (choice?.outcome === "accepted") {
    showToast("Installing PlanPal...");
  }
}

function updateInstallAvailability() {
  const isInstalled = window.matchMedia?.("(display-mode: standalone)")?.matches || window.navigator.standalone === true;
  document.body.classList.toggle("app-installed", Boolean(isInstalled));

  for (const button of [elements.installAppButton, elements.mobileInstallButton]) {
    if (!button) continue;
    const shouldShow = !isInstalled;
    button.classList.toggle("hidden", !shouldShow);
    button.classList.toggle("is-available", shouldShow);
  }
}

function showInstallHelp() {
  if (!window.isSecureContext && !isLocalhost()) {
    showToast("Real app install needs HTTPS. Use a hosted HTTPS URL, then open Chrome menu > Install app.");
    return;
  }

  const isIos = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const message = isIos
    ? "On iPhone, tap Share, then Add to Home Screen."
    : "Open Chrome menu, then tap Install app or Add to Home screen.";
  showToast(message);
}

function isLocalhost() {
  return ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
}

async function handleParse() {
  if (entryMode === "manual") {
    openManualTask();
    return;
  }

  const userInput = elements.taskInput.value.trim();
  if (!userInput) return;

  setBusy(true, "Parsing your task...");
  clearError();

  try {
    const response = await fetch(`${API_BASE}/api/tasks/parse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_input: userInput, user_id: currentUserId }),
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Parsing failed");
    }

    pendingEntryMode = "auto";
    pendingTask = normalizeTask(data.task);
    fillReviewPanel(pendingTask, pendingTask.follow_up_questions || []);
    elements.reviewPanel.classList.remove("hidden");
    elements.reviewPanel.classList.add("flex");
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}

async function handleApplyDetails() {
  if (!pendingTask) return;

  if (pendingTask.id) {
    await deleteTask(pendingTask.id);
    resetPendingTask();
    return;
  }

  pendingTask = taskFromReview();
  const answers = collectFollowUpAnswers(pendingTask.missing_info || []);

  if (Object.keys(answers).length === 0) {
    updateMissingInfo(pendingTask.missing_info || []);
    renderFollowUps(pendingTask.follow_up_questions || []);
    showToast("Details updated");
    return;
  }

  setBusy(true, "Applying details...");
  clearError();

  try {
    const response = await fetch(`${API_BASE}/api/tasks/follow-up`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task: pendingTask, answers, user_id: currentUserId }),
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Could not apply follow-up answers");
    }

    pendingTask = { ...normalizeTask(data.task), ...editableMetadataFromReview() };
    fillReviewPanel(pendingTask, pendingTask.follow_up_questions || []);
    updateMissingInfo(pendingTask.missing_info || []);
    showToast(pendingTask.missing_info?.length ? "More details needed" : "Details applied");
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}

async function handleConfirm() {
  if (!pendingTask) return;

  const task = taskFromReview();
  const manualMissing = pendingEntryMode === "manual" ? missingManualFields(task) : [];
  if (manualMissing.length > 0) {
    showError(`Manual mode needs: ${manualMissing.join(", ")}.`);
    return;
  }

  if (!task.title.trim()) {
    showError("Please add a title before confirming.");
    return;
  }

  saveProjectColor(task.project, elements.projectColorInput.value);
  setBusy(true, "Saving task...");
  clearError();

  try {
    const isEditingExistingTask = Boolean(task.id);
    const response = await fetch(
      isEditingExistingTask ? `${API_BASE}/api/tasks/${task.id}` : `${API_BASE}/api/tasks/confirm`,
      {
        method: isEditingExistingTask ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(isEditingExistingTask ? taskPatchPayload(task) : { task, user_id: currentUserId }),
      },
    );
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Could not save task");
    }

    resetPendingTask();
    elements.taskInput.value = "";
    showToast(isEditingExistingTask ? "Item updated" : "Item added");
    await loadTasks({ quiet: true });
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}

async function loadTasks(options = {}) {
  setSyncDisabled(true);

  try {
    const response = await fetch(`${API_BASE}/api/tasks?user_id=${encodeURIComponent(currentUserId)}`);
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Could not load tasks");
    }

    tasks = (data.tasks || []).map(normalizeTask);
    refreshProjectOptions();
    renderTasks();
    if (!options.quiet) showToast("Tasks synced");
  } catch (error) {
    showError(error.message);
  } finally {
    setSyncDisabled(false);
  }
}

function renderTasks() {
  const grouped = groupTasks(tasks);

  renderDatedList(listElements.tasks, grouped.tasks, { kind: "task" });
  renderDatedList(listElements.events, grouped.events, { kind: "event" });
  renderCalendar(grouped.datedItems);
  renderList(listElements.archive, grouped.archive, { archivedView: true });
  renderProjects(grouped.projects);

  toggleEmpty(emptyElements.tasks, grouped.tasks.length === 0);
  toggleEmpty(emptyElements.events, grouped.events.length === 0);
  toggleEmpty(emptyElements.archive, grouped.archive.length === 0);
  toggleEmpty(emptyElements.projects, grouped.projects.size === 0);
}

function groupTasks(taskList) {
  const grouped = {
    active: [],
    tasks: [],
    events: [],
    datedItems: new Map(),
    archive: [],
    projects: new Map(),
  };

  for (const task of taskList) {
    if (task.archived) {
      grouped.archive.push(task);
      continue;
    }

    grouped.active.push(task);

    if (isEvent(task)) {
      grouped.events.push(task);
    } else {
      grouped.tasks.push(task);
    }

    if (task.date) {
      if (!grouped.datedItems.has(task.date)) {
        grouped.datedItems.set(task.date, []);
      }
      grouped.datedItems.get(task.date).push(task);
    }

    const project = task.project || "project";
    if (!grouped.projects.has(project)) {
      grouped.projects.set(project, []);
    }
    grouped.projects.get(project).push(task);
  }

  return grouped;
}

function isEvent(task) {
  return Boolean(task.all_day) || (task.duration != null && Number(task.duration) > 0);
}

function renderList(container, taskList, options = {}) {
  container.innerHTML = "";
  for (const task of taskList) {
    container.append(renderTaskCard(task, options));
  }
}

function renderDatedList(container, taskList, options = {}) {
  container.innerHTML = "";

  for (const [dateKey, dateTasks] of groupTasksByDate(taskList)) {
    const section = document.createElement("section");
    section.className = "task-date-group flex flex-col gap-sm";

    const heading = document.createElement("div");
    heading.className = "task-date-heading flex items-center justify-between gap-md";

    const title = document.createElement("h4");
    title.className = "font-label-sm text-outline uppercase";
    title.textContent = formatDateGroupLabel(dateKey);

    const count = document.createElement("span");
    count.className = "text-[11px] bg-surface-container-high px-sm py-xs rounded text-outline uppercase font-bold";
    count.textContent = `${dateTasks.length} ${dateTasks.length === 1 ? "item" : "items"}`;

    const list = document.createElement("div");
    list.className = "flex flex-col gap-sm";

    for (const task of sortTasksByDateTime(dateTasks)) {
      list.append(renderTaskCard(task, options));
    }

    heading.append(title, count);
    section.append(heading, list);
    container.append(section);
  }
}

function groupTasksByDate(taskList) {
  const groups = new Map();

  for (const task of taskList) {
    const dateKey = task.date || "no-date";
    if (!groups.has(dateKey)) {
      groups.set(dateKey, []);
    }
    groups.get(dateKey).push(task);
  }

  return [...groups.entries()].sort(([dateA], [dateB]) => {
    if (dateA === "no-date") return 1;
    if (dateB === "no-date") return -1;
    return dateA.localeCompare(dateB);
  });
}

function sortTasksByDateTime(taskList) {
  return [...taskList].sort((a, b) => {
    const timeCompare = (a.time || "").localeCompare(b.time || "");
    if (timeCompare !== 0) return timeCompare;
    return (a.title || "").localeCompare(b.title || "");
  });
}

function formatDateGroupLabel(dateKey) {
  if (dateKey === "no-date") return "No Date";

  const [year, month, day] = dateKey.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  if (Number.isNaN(date.getTime())) return dateKey;

  const today = new Date();
  const tomorrow = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
  const dateLabel = date.toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
  });

  if (dateKey === localDateKey(today)) return `Today · ${dateLabel}`;
  if (dateKey === localDateKey(tomorrow)) return `Tomorrow · ${dateLabel}`;
  return dateLabel;
}

function renderProjects(projectGroups) {
  listElements.projects.innerHTML = "";

  for (const [project, projectTasks] of [...projectGroups.entries()].sort(([a], [b]) => a.localeCompare(b))) {
    const section = document.createElement("section");
    section.className = "flex flex-col gap-sm";

    const heading = document.createElement("div");
    heading.className = "flex items-center justify-between gap-md";

    const title = document.createElement("h4");
    title.className = "font-headline-md text-on-surface";
    title.textContent = project;

    const count = document.createElement("span");
    count.className = "text-[11px] bg-surface-container-high px-sm py-xs rounded text-outline uppercase font-bold";
    const goalCount = projectTasks.filter((task) => !isEvent(task)).length;
    const eventCount = projectTasks.length - goalCount;
    count.textContent = `${goalCount} goal${goalCount === 1 ? "" : "s"} · ${eventCount} event${eventCount === 1 ? "" : "s"}`;

    count.style.backgroundColor = projectTint(project);
    count.style.color = projectColor(project);

    const colorInput = document.createElement("input");
    colorInput.className = "w-10 h-8 border border-outline-variant rounded bg-surface-container-lowest";
    colorInput.type = "color";
    colorInput.value = projectColor(project);
    colorInput.title = `Change ${project} color`;
    colorInput.addEventListener("input", () => {
      saveProjectColor(project, colorInput.value);
      renderTasks();
    });

    const list = document.createElement("div");
    list.className = "flex flex-col gap-sm";
    renderList(list, projectTasks);

    const controls = document.createElement("div");
    controls.className = "flex items-center gap-sm";
    controls.append(count, colorInput);

    heading.append(title, controls);
    section.append(heading, list);
    listElements.projects.append(section);
  }
}

function renderCalendar(calendarGroups) {
  listElements.calendar.innerHTML = "";
  listElements.calendarWeekDayScroller.innerHTML = "";
  listElements.calendarWeekAgenda.innerHTML = "";
  listElements.calendarSchedule.innerHTML = "";
  const year = calendarCursor.getFullYear();
  const month = calendarCursor.getMonth();
  const firstDay = new Date(year, month, 1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const leadingBlanks = firstDay.getDay();
  const today = new Date().toISOString().slice(0, 10);

  updateCalendarModeButtons();
  elements.calendarMonthLabel.textContent = calendarMode === "month"
    ? firstDay.toLocaleDateString(undefined, { month: "long", year: "numeric" })
    : calendarMode === "week"
      ? formatWeekLabel(calendarCursor)
      : "Schedule";

  const isSchedule = calendarMode === "schedule";
  const isWeek = calendarMode === "week";
  setCalendarModeClasses(calendarMode);

  if (isSchedule) {
    renderCalendarSchedule(calendarGroups);
    toggleEmpty(emptyElements.calendar, calendarGroups.size === 0);
    renderSelectedDayDetails(calendarGroups.get(selectedCalendarDate) || []);
    return;
  }

  const visibleDates = calendarMode === "month"
    ? getMonthVisibleDates(year, month, leadingBlanks, daysInMonth)
    : getWeekVisibleDates(calendarCursor);

  if (isWeek && !calendarGroups.has(selectedCalendarDate)) {
    selectedCalendarDate = localDateKey(calendarCursor);
  }

  if (isWeek) {
    renderWeekTimeGrid(visibleDates, calendarGroups, today);
    renderSelectedDayDetails(calendarGroups.get(selectedCalendarDate) || []);
    toggleEmpty(emptyElements.calendar, false);
    return;
  }

  for (const visibleDate of visibleDates) {
    const isOutsideMonth = calendarMode === "month" && visibleDate.getMonth() !== month;
    listElements.calendar.append(renderCalendarDay(visibleDate, calendarGroups, today, { isOutsideMonth }));
  }

  const visibleKeys = new Set(visibleDates.map(localDateKey));
  toggleEmpty(emptyElements.calendar, ![...calendarGroups.keys()].some((date) => visibleKeys.has(date)));
  renderSelectedDayDetails(calendarGroups.get(selectedCalendarDate) || []);
}

function setCalendarModeClasses(mode) {
  const weekdays = document.querySelector("#calendar-weekdays");

  if (mode === "schedule") {
    listElements.calendar.style.gridTemplateColumns = "";
    listElements.calendar.className = "hidden";
    listElements.calendarWeekDayScroller.className = "hidden";
    listElements.calendarWeekAgenda.className = "hidden";
    listElements.calendarSchedule.className = "flex flex-col gap-md p-md";
    if (weekdays) weekdays.className = "hidden";
    return;
  }

  listElements.calendarSchedule.className = "hidden";

  if (mode === "week") {
    listElements.calendar.className = "week-time-grid bg-outline-variant";
    listElements.calendarWeekDayScroller.className = "hidden";
    listElements.calendarWeekAgenda.className = "hidden";
    if (weekdays) {
      weekdays.className = "hidden";
    }
    return;
  }

  listElements.calendar.style.gridTemplateColumns = "";
  listElements.calendar.className = "grid grid-cols-7 bg-outline-variant gap-[1px]";
  listElements.calendarWeekDayScroller.className = "hidden";
  listElements.calendarWeekAgenda.className = "hidden";
  if (weekdays) {
    weekdays.className = "grid grid-cols-7 border-b border-outline-variant bg-surface-container-lowest";
  }
}

function renderWeekDayScroller(visibleDates, calendarGroups) {
  for (const date of visibleDates) {
    const dateKey = localDateKey(date);
    const items = calendarGroups.get(dateKey) || [];
    const isSelected = dateKey === selectedCalendarDate;

    const button = document.createElement("button");
    button.className = "flex-none flex flex-col items-center justify-center rounded-xl transition-all";
    button.classList.add(
      isSelected ? "w-14" : "w-12",
      isSelected ? "h-20" : "h-16",
      "md:w-full",
      "md:h-20",
      "md:flex-none",
      isSelected ? "bg-primary" : "bg-surface-container-low",
      isSelected ? "text-on-primary" : "text-on-surface-variant",
      isSelected ? "shadow-md" : "shadow-none",
    );
    button.type = "button";
    button.addEventListener("click", () => {
      selectedCalendarDate = dateKey;
      calendarCursor = date;
      renderTasks();
    });

    const weekday = document.createElement("span");
    weekday.className = "text-label-sm font-medium";
    weekday.textContent = date.toLocaleDateString(undefined, { weekday: "short" }).toUpperCase();

    const day = document.createElement("span");
    day.className = isSelected ? "text-headline-md font-bold" : "text-body-lg font-bold";
    day.textContent = String(date.getDate());

    button.append(weekday, day);
    if (items.length > 0) {
      const dot = document.createElement("div");
      dot.className = `w-1.5 h-1.5 rounded-full mt-xs ${isSelected ? "bg-on-primary" : "bg-primary"}`;
      button.append(dot);
    }
    listElements.calendarWeekDayScroller.append(button);
  }
}

function renderWeekAgenda(items) {
  const goals = items.filter((task) => !isEvent(task));
  const events = items.filter(isEvent).sort((a, b) => (a.time || "").localeCompare(b.time || ""));
  const selected = new Date(`${selectedCalendarDate}T00:00:00`);

  const heading = document.createElement("div");
  heading.className = "flex items-center justify-between";

  const title = document.createElement("h2");
  title.className = "font-headline-md text-on-surface font-semibold";
  title.textContent = selected.toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" });

  const monthButton = document.createElement("button");
  monthButton.className = "p-xs text-primary";
  monthButton.type = "button";
  monthButton.append(icon("calendar_month"));
  monthButton.addEventListener("click", () => setCalendarMode("month"));

  heading.append(title, monthButton);
  listElements.calendarWeekAgenda.append(heading);

  const ordered = [...events, ...goals];
  if (ordered.length === 0) {
    const empty = document.createElement("div");
    empty.className = "py-xl text-center border-2 border-dashed border-outline-variant rounded-xl text-outline";
    empty.textContent = "No goals or events for this day.";
    listElements.calendarWeekAgenda.append(empty);
    return;
  }

  for (const item of ordered) {
    if (isEvent(item)) {
      listElements.calendarWeekAgenda.append(renderMobileEventCard(item));
    } else {
      listElements.calendarWeekAgenda.append(renderMobileGoalCard(item));
    }
  }
}

function renderMobileEventCard(event) {
  const card = document.createElement("button");
  card.className = "relative border-l-4 p-md rounded-r-xl active:scale-[0.98] transition-transform text-left";
  card.style.backgroundColor = projectTint(event.project);
  card.style.borderLeftColor = projectColor(event.project);
  card.type = "button";
  card.addEventListener("click", () => openEditTask(event));

  const label = document.createElement("span");
  label.className = "text-label-md font-bold uppercase";
  label.style.color = projectColor(event.project);
  label.textContent = ["Event", event.time, event.all_day ? "All day" : formatDuration(event.duration)].filter(Boolean).join(" - ");

  const title = document.createElement("h3");
  title.className = "font-headline-md text-on-surface font-semibold mt-xs";
  title.textContent = event.title || "Untitled event";

  card.append(label, title);
  return card;
}

function renderMobileGoalCard(goal) {
  const card = document.createElement("button");
  card.className = "bg-surface-container-low border border-outline-variant p-md rounded-xl active:scale-[0.98] transition-transform text-left";
  card.style.borderLeft = `4px solid ${projectColor(goal.project)}`;
  card.type = "button";
  card.addEventListener("click", () => openEditTask(goal));

  const row = document.createElement("div");
  row.className = "flex gap-md items-center";

  const check = document.createElement("span");
  check.className = "w-6 h-6 rounded-md border-2 border-outline-variant shrink-0";
  check.style.borderColor = projectColor(goal.project);

  const content = document.createElement("div");
  content.className = "flex-1";

  const title = document.createElement("h3");
  title.className = "font-body-lg text-on-surface font-medium";
  title.textContent = goal.title || "Untitled goal";

  const meta = document.createElement("div");
  meta.className = "flex items-center gap-md mt-xs";
  const badge = document.createElement("span");
  badge.className = "px-sm py-0.5 bg-surface-container-high text-on-surface-variant text-[10px] font-bold rounded uppercase";
  badge.textContent = goal.project || "project";
  badge.style.backgroundColor = projectTint(goal.project);
  badge.style.color = projectColor(goal.project);
  meta.append(badge);

  content.append(title, meta);
  row.append(check, content);
  card.append(row);
  return card;
}

function renderCalendarSchedule(calendarGroups) {
  const sortedDates = [...calendarGroups.keys()].sort();

  for (const date of sortedDates) {
    const items = calendarGroups.get(date).slice().sort((a, b) => {
      if (isEvent(a) !== isEvent(b)) return isEvent(a) ? 1 : -1;
      return (a.time || "").localeCompare(b.time || "");
    });

    const section = document.createElement("section");
    section.className = "bg-surface-container-lowest border border-outline-variant rounded-lg p-md flex flex-col gap-sm";

    const heading = document.createElement("button");
    heading.className = "flex items-center justify-between text-left border-b border-outline-variant pb-sm";
    heading.type = "button";
    heading.addEventListener("click", () => {
      selectedCalendarDate = date;
      renderTasks();
    });

    const title = document.createElement("h4");
    title.className = "font-headline-md text-on-surface";
    title.textContent = new Date(`${date}T00:00:00`).toLocaleDateString(undefined, {
      weekday: "long",
      month: "short",
      day: "numeric",
      year: "numeric",
    });

    const count = document.createElement("span");
    count.className = "text-[11px] bg-primary-fixed text-on-primary-fixed px-sm py-xs rounded uppercase font-bold";
    count.textContent = `${items.length} item${items.length === 1 ? "" : "s"}`;

    const list = document.createElement("div");
    list.className = "flex flex-col gap-sm";
    renderList(list, items);

    heading.append(title, count);
    section.append(heading, list);
    listElements.calendarSchedule.append(section);
  }
}

function renderWeekTimeGrid(visibleDates, calendarGroups, today) {
  const visibleKeys = visibleDates.map(localDateKey);
  const weekItems = visibleKeys.flatMap((dateKey) => calendarGroups.get(dateKey) || []);
  const { startHour, endHour } = getWeekHourRange(weekItems);

  listElements.calendar.style.gridTemplateColumns = "52px repeat(7, minmax(112px, 1fr))";

  const corner = document.createElement("div");
  corner.className = "week-time-corner bg-surface-container-lowest border-r border-b border-outline-variant";
  listElements.calendar.append(corner);

  for (const date of visibleDates) {
    const dateKey = localDateKey(date);
    const dayHeader = document.createElement("button");
    dayHeader.className = "week-time-day-header bg-surface-container-lowest border-b border-outline-variant p-sm text-left";
    dayHeader.type = "button";
    dayHeader.addEventListener("click", () => {
      selectedCalendarDate = dateKey;
      calendarCursor = date;
      renderTasks();
    });
    if (dateKey === today) dayHeader.classList.add("bg-primary-fixed");
    if (dateKey === selectedCalendarDate) dayHeader.classList.add("outline", "outline-2", "outline-primary");

    const weekday = document.createElement("div");
    weekday.className = "font-label-sm text-outline uppercase";
    weekday.textContent = date.toLocaleDateString(undefined, { weekday: "short" });

    const day = document.createElement("div");
    day.className = "font-body-md font-bold text-on-surface";
    day.textContent = date.toLocaleDateString(undefined, { month: "short", day: "numeric" });

    dayHeader.append(weekday, day);
    listElements.calendar.append(dayHeader);
  }

  appendWeekTimeRow("All day", visibleDates, calendarGroups, (item) => !item.time);

  for (let hour = startHour; hour <= endHour; hour += 1) {
    appendWeekTimeRow(formatHourLabel(hour), visibleDates, calendarGroups, (item) => timeHour(item.time) === hour);
  }
}

function appendWeekTimeRow(label, visibleDates, calendarGroups, itemFilter) {
  const timeLabel = document.createElement("div");
  timeLabel.className = "week-time-label bg-surface-container-lowest border-r border-b border-outline-variant p-xs text-label-md text-outline";
  timeLabel.textContent = label;
  listElements.calendar.append(timeLabel);

  for (const date of visibleDates) {
    const dateKey = localDateKey(date);
    const cellItems = (calendarGroups.get(dateKey) || []).filter(itemFilter).sort(compareWeekGridItems);
    const cell = document.createElement("button");
    cell.className = "week-time-cell bg-white border-b border-outline-variant p-xs text-left";
    cell.type = "button";
    cell.addEventListener("click", () => {
      selectedCalendarDate = dateKey;
      calendarCursor = date;
      renderTasks();
    });

    for (const item of cellItems) {
      cell.append(renderWeekTimeGridItem(item));
    }

    listElements.calendar.append(cell);
  }
}

function renderWeekTimeGridItem(item) {
  const button = document.createElement("button");
  button.className = "week-time-item text-left rounded px-xs py-xs shadow-sm";
  button.type = "button";
  button.style.backgroundColor = isEvent(item) ? projectColor(item.project) : projectTint(item.project);
  button.style.color = isEvent(item) ? "#ffffff" : projectColor(item.project);
  button.addEventListener("click", (clickEvent) => {
    clickEvent.stopPropagation();
    openEditTask(item);
  });

  const meta = document.createElement("div");
  meta.className = "week-time-item-meta font-label-sm";
  meta.textContent = formatWeekItemMeta(item);

  const title = document.createElement("div");
  title.className = "week-time-item-title font-label-md";
  title.textContent = item.title || (isEvent(item) ? "Untitled event" : "Untitled goal");

  button.append(meta, title);
  return button;
}

function getWeekHourRange(items) {
  const hours = items.map((item) => timeHour(item.time)).filter((hour) => hour != null);
  if (hours.length === 0) return { startHour: 8, endHour: 18 };

  const minHour = Math.min(...hours);
  const maxHour = Math.max(...hours);
  return {
    startHour: Math.max(0, Math.min(8, minHour)),
    endHour: Math.min(23, Math.max(18, maxHour)),
  };
}

function timeHour(time) {
  if (!time) return null;
  const [hour] = String(time).split(":").map(Number);
  return Number.isFinite(hour) ? hour : null;
}

function formatHourLabel(hour) {
  return `${String(hour).padStart(2, "0")}:00`;
}

function compareWeekGridItems(a, b) {
  const timeCompare = (a.time || "").localeCompare(b.time || "");
  if (timeCompare !== 0) return timeCompare;
  if (isEvent(a) !== isEvent(b)) return isEvent(a) ? -1 : 1;
  return (a.title || "").localeCompare(b.title || "");
}

function renderCalendarDay(date, calendarGroups, today, options = {}) {
  const dateKey = localDateKey(date);
  const items = (calendarGroups.get(dateKey) || []).slice();
  const dayTasks = items.filter((task) => !isEvent(task));
  const dayEvents = items.filter(isEvent).sort((a, b) => (a.time || "").localeCompare(b.time || ""));

  const cell = document.createElement("button");
  cell.className = "min-h-[145px] bg-white p-sm flex flex-col gap-xs overflow-hidden text-left hover:bg-surface-bright transition-colors";
  cell.type = "button";
  if (calendarMode === "week") cell.classList.add("min-h-[420px]");
  if (options.isOutsideMonth) cell.classList.add("bg-surface-container-low", "opacity-60");
  if (dateKey === today) cell.classList.add("bg-primary-fixed", "ring-2", "ring-primary");
  if (dateKey === selectedCalendarDate) cell.classList.add("outline", "outline-2", "outline-primary");
  cell.addEventListener("click", () => {
    selectedCalendarDate = dateKey;
    renderTasks();
  });

  const header = document.createElement("div");
  header.className = "flex items-center justify-between";

  const dayNumber = document.createElement("span");
  dayNumber.className = "font-label-md text-on-surface";
  dayNumber.textContent = calendarMode === "week"
    ? date.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })
    : String(date.getDate());

  const count = document.createElement("span");
  count.className = "text-[10px] text-outline";
  count.textContent = items.length ? `${items.length}` : "";

  header.append(dayNumber, count);
  cell.append(header);

  if (calendarMode === "month" && isPhoneLayout()) {
    renderCompactMonthItems(cell, [...dayEvents, ...dayTasks]);
    return cell;
  }

  if (calendarMode === "week") {
    const weekItems = sortTasksForWeek(items);
    const weekList = document.createElement("div");
    weekList.className = "week-day-items flex flex-col gap-xs";

    if (weekItems.length === 0) {
      const empty = document.createElement("span");
      empty.className = "week-empty text-[11px] text-outline";
      empty.textContent = "No items";
      weekList.append(empty);
    }

    for (const item of weekItems) {
      weekList.append(renderWeekCalendarItem(item));
    }

    cell.append(weekList);
    return cell;
  }

  if (dayTasks.length > 0) {
    const taskList = document.createElement("div");
    taskList.className = "flex flex-col gap-xs";
    const taskLimit = calendarMode === "week" ? 8 : 3;
    for (const task of dayTasks.slice(0, taskLimit)) {
      const taskItem = document.createElement("div");
      taskItem.className = "flex items-center gap-xs text-[11px] leading-4 truncate rounded px-xs py-xs";
      taskItem.style.backgroundColor = projectTint(task.project);
      taskItem.style.color = projectColor(task.project);
      const checkbox = document.createElement("span");
      checkbox.className = "w-3 h-3 rounded border bg-white shrink-0";
      checkbox.style.borderColor = projectColor(task.project);
      const label = document.createElement("span");
      label.className = "truncate";
      label.textContent = task.title || "Untitled goal";
      taskItem.append(checkbox, label);
      taskList.append(taskItem);
    }
    if (dayTasks.length > taskLimit) {
      const more = document.createElement("span");
      more.className = "text-[10px] text-outline";
      more.textContent = `+${dayTasks.length - taskLimit} goal${dayTasks.length - taskLimit === 1 ? "" : "s"}`;
      taskList.append(more);
    }
    cell.append(taskList);
  }

  const eventStack = document.createElement("div");
  eventStack.className = "flex flex-col gap-xs mt-xs";
  const eventLimit = calendarMode === "week" ? 10 : 4;
  for (const event of dayEvents.slice(0, eventLimit)) {
    const eventButton = document.createElement("button");
    const durationMinutes = event.all_day
      ? 28
      : Math.max(20, Math.min(calendarMode === "week" ? 150 : 90, Math.round(Number(event.duration) * 28)));
    eventButton.className = "text-left rounded px-xs py-xs shadow-sm overflow-hidden";
    eventButton.style.backgroundColor = projectColor(event.project);
    eventButton.style.color = "#ffffff";
    eventButton.style.minHeight = `${durationMinutes}px`;
    eventButton.type = "button";
    eventButton.addEventListener("click", (clickEvent) => {
      clickEvent.stopPropagation();
      openEditTask(event);
    });

    const title = document.createElement("div");
    title.className = "text-[11px] font-semibold leading-4 truncate";
    title.textContent = event.title || "Untitled event";

    const meta = document.createElement("div");
    meta.className = "text-[10px] opacity-90";
    meta.textContent = [event.time, event.all_day ? "All day" : formatDuration(event.duration)].filter(Boolean).join(" - ");

    eventButton.append(title, meta);
    eventStack.append(eventButton);
  }
  if (dayEvents.length > eventLimit) {
    const more = document.createElement("span");
    more.className = "text-[10px] text-outline";
    more.textContent = `+${dayEvents.length - eventLimit} more event${dayEvents.length - eventLimit === 1 ? "" : "s"}`;
    eventStack.append(more);
  }
  cell.append(eventStack);
  return cell;
}

function renderCompactMonthItems(cell, items) {
  if (items.length === 0) return;

  const indicatorList = document.createElement("div");
  indicatorList.className = "month-compact-items";

  for (const item of sortTasksForWeek(items).slice(0, 3)) {
    const indicator = document.createElement("div");
    indicator.className = "month-compact-item";
    indicator.style.backgroundColor = isEvent(item) ? projectColor(item.project) : projectTint(item.project);
    indicator.style.color = isEvent(item) ? "#ffffff" : projectColor(item.project);
    indicator.textContent = [item.time, item.title || (isEvent(item) ? "Untitled event" : "Untitled goal")]
      .filter(Boolean)
      .join(" ");
    indicator.title = indicator.textContent;
    indicatorList.append(indicator);
  }

  if (items.length > 3) {
    const more = document.createElement("span");
    more.className = "month-compact-more";
    more.textContent = `+${items.length - 3}`;
    indicatorList.append(more);
  }

  cell.append(indicatorList);
}

function isPhoneLayout() {
  return window.matchMedia?.("(max-width: 760px)")?.matches;
}

function sortTasksForWeek(taskList) {
  return [...taskList].sort((a, b) => {
    const aHasTime = Boolean(a.time);
    const bHasTime = Boolean(b.time);
    if (aHasTime !== bHasTime) return aHasTime ? -1 : 1;

    const timeCompare = (a.time || "").localeCompare(b.time || "");
    if (timeCompare !== 0) return timeCompare;

    if (isEvent(a) !== isEvent(b)) return isEvent(a) ? -1 : 1;
    return (a.title || "").localeCompare(b.title || "");
  });
}

function renderWeekCalendarItem(item) {
  const button = document.createElement("button");
  button.className = "week-calendar-item text-left rounded px-xs py-xs shadow-sm overflow-hidden";
  button.type = "button";
  button.style.backgroundColor = isEvent(item) ? projectColor(item.project) : projectTint(item.project);
  button.style.color = isEvent(item) ? "#ffffff" : projectColor(item.project);
  button.addEventListener("click", (clickEvent) => {
    clickEvent.stopPropagation();
    openEditTask(item);
  });

  const meta = document.createElement("div");
  meta.className = "week-calendar-item-meta font-label-sm";
  meta.textContent = formatWeekItemMeta(item);

  const title = document.createElement("div");
  title.className = "week-calendar-item-title font-label-md";
  title.textContent = item.title || (isEvent(item) ? "Untitled event" : "Untitled goal");

  button.append(meta, title);
  return button;
}

function formatWeekItemMeta(item) {
  const parts = [item.time || "Any time"];
  if (isEvent(item)) {
    if (item.all_day) {
      parts.push("All day");
    } else if (item.duration) {
      parts.push(formatDuration(item.duration));
    }
  }
  parts.push(isEvent(item) ? "Event" : "Goal");
  return parts.join(" - ");
}

function renderSelectedDayDetails(items) {
  const goals = items.filter((task) => !isEvent(task));
  const events = items.filter(isEvent).sort((a, b) => (a.time || "").localeCompare(b.time || ""));
  const selected = new Date(`${selectedCalendarDate}T00:00:00`);

  elements.calendarSelectedDate.textContent = selected.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  elements.calendarSelectedSummary.textContent = `${goals.length} Goal${goals.length === 1 ? "" : "s"} · ${events.length} Event${events.length === 1 ? "" : "s"}`;
  elements.calendarSelectedList.innerHTML = "";

  for (const item of [...events, ...goals]) {
    const row = document.createElement("button");
    row.className = "w-full flex items-center gap-md text-left";
    row.type = "button";
    row.addEventListener("click", () => openEditTask(item));

    const dot = document.createElement("span");
    dot.className = "w-2 h-2 rounded-full shrink-0";
    dot.style.backgroundColor = projectColor(item.project);

    const title = document.createElement("span");
    title.className = "text-body-md text-on-surface truncate";
    title.textContent = item.title || (isEvent(item) ? "Untitled event" : "Untitled goal");

    const meta = document.createElement("span");
    meta.className = "ml-auto text-label-md text-on-surface-variant";
    meta.textContent = isEvent(item) ? [item.time, item.all_day ? "All day" : formatDuration(item.duration)].filter(Boolean).join(" ") : "Goal";

    row.append(dot, title, meta);
    elements.calendarSelectedList.append(row);
  }

  if (items.length === 0) {
    const empty = document.createElement("p");
    empty.className = "text-body-md text-on-surface-variant";
    empty.textContent = "No goals or events on this day.";
    elements.calendarSelectedList.append(empty);
  }
}

function shiftCalendarMonth(delta) {
  if (calendarMode === "week") {
    calendarCursor = new Date(calendarCursor.getFullYear(), calendarCursor.getMonth(), calendarCursor.getDate() + delta * 7);
  } else {
    calendarCursor = new Date(calendarCursor.getFullYear(), calendarCursor.getMonth() + delta, 1);
  }
  renderTasks();
}

function setCalendarMode(mode) {
  calendarMode = mode;
  renderTasks();
}

function updateCalendarModeButtons() {
  const isMonth = calendarMode === "month";
  const isWeek = calendarMode === "week";
  const isSchedule = calendarMode === "schedule";
  elements.calendarMonthModeButton.classList.toggle("bg-white", isMonth);
  elements.calendarMonthModeButton.classList.toggle("text-primary", isMonth);
  elements.calendarMonthModeButton.classList.toggle("shadow-sm", isMonth);
  elements.calendarMonthModeButton.classList.toggle("text-on-surface-variant", !isMonth);

  elements.calendarWeekModeButton.classList.toggle("bg-white", isWeek);
  elements.calendarWeekModeButton.classList.toggle("text-primary", isWeek);
  elements.calendarWeekModeButton.classList.toggle("shadow-sm", isWeek);
  elements.calendarWeekModeButton.classList.toggle("text-on-surface-variant", !isWeek);

  elements.calendarScheduleModeButton.classList.toggle("bg-white", isSchedule);
  elements.calendarScheduleModeButton.classList.toggle("text-primary", isSchedule);
  elements.calendarScheduleModeButton.classList.toggle("shadow-sm", isSchedule);
  elements.calendarScheduleModeButton.classList.toggle("text-on-surface-variant", !isSchedule);
}

function getMonthVisibleDates(year, month, leadingBlanks, daysInMonth) {
  const dates = [];
  const firstVisible = new Date(year, month, 1 - leadingBlanks);
  const totalCells = Math.ceil((leadingBlanks + daysInMonth) / 7) * 7;
  for (let index = 0; index < totalCells; index += 1) {
    dates.push(new Date(firstVisible.getFullYear(), firstVisible.getMonth(), firstVisible.getDate() + index));
  }
  return dates;
}

function getWeekVisibleDates(date) {
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate() - date.getDay());
  return Array.from({ length: 7 }, (_, index) => (
    new Date(start.getFullYear(), start.getMonth(), start.getDate() + index)
  ));
}

function formatWeekLabel(date) {
  const week = getWeekVisibleDates(date);
  const start = week[0];
  const end = week[6];
  const sameMonth = start.getMonth() === end.getMonth() && start.getFullYear() === end.getFullYear();
  if (sameMonth) {
    return `${start.toLocaleDateString(undefined, { month: "long" })} ${start.getDate()}-${end.getDate()}, ${start.getFullYear()}`;
  }
  return `${start.toLocaleDateString(undefined, { month: "short", day: "numeric" })} - ${end.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;
}

function localDateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function renderTaskCard(task, options = {}) {
  const item = document.createElement("article");
  item.className = [
    "task-card bg-surface-container-lowest border border-outline-variant p-md rounded-lg",
    "flex items-center gap-md group hover:border-primary transition-colors",
    task.completed ? "opacity-70" : "",
    options.archivedView ? "grayscale" : "",
  ].join(" ");
  item.style.borderLeft = `4px solid ${projectColor(task.project)}`;

  const checkbox = document.createElement("input");
  checkbox.className = "w-5 h-5 rounded border-outline text-secondary focus:ring-secondary cursor-pointer";
  checkbox.type = "checkbox";
  checkbox.checked = Boolean(task.completed);
  checkbox.disabled = Boolean(task.archived);
  checkbox.addEventListener("change", () => {
    const updates = checkbox.checked ? { completed: true, archived: true } : { completed: false };
    updateTask(task.id, updates);
  });

  const content = document.createElement("div");
  content.className = "flex-1 min-w-0";

  const titleRow = document.createElement("div");
  titleRow.className = "flex items-center gap-sm flex-wrap";

  const title = document.createElement("p");
  title.className = `font-body-md font-medium text-on-surface break-words${task.completed ? " line-through" : ""}`;
  title.textContent = task.title || "Untitled goal";
  titleRow.append(title);

  if (task.project) {
    const badge = document.createElement("span");
    badge.className = "text-[10px] bg-surface-container-high px-1.5 py-0.5 rounded text-outline uppercase font-bold";
    badge.textContent = task.project;
    badge.style.backgroundColor = projectTint(task.project);
    badge.style.color = projectColor(task.project);
    titleRow.append(badge);
  }

  content.append(titleRow);

  const typeBadge = document.createElement("span");
  typeBadge.className = "inline-flex mt-xs text-[10px] px-1.5 py-0.5 rounded uppercase font-bold";
  typeBadge.style.backgroundColor = projectTint(task.project);
  typeBadge.style.color = projectColor(task.project);
  typeBadge.textContent = isEvent(task) ? "Event" : "Goal";
  content.append(typeBadge);

  if (task.description && task.description !== task.title) {
    const description = document.createElement("p");
    description.className = "text-[12px] text-on-surface-variant mt-xs break-words";
    description.textContent = task.description;
    content.append(description);
  }

  const meta = formatMeta(task);
  if (meta.length > 0) {
    const metaRow = document.createElement("div");
    metaRow.className = "flex gap-md mt-xs text-[12px] text-outline flex-wrap";
    for (const part of meta) {
      const span = document.createElement("span");
      span.className = "flex items-center gap-xs";
      span.append(icon(part.icon), document.createTextNode(part.text));
      metaRow.append(span);
    }
    content.append(metaRow);
  }

  const actions = document.createElement("div");
  actions.className = "flex items-center gap-sm opacity-100 sm:opacity-0 group-hover:opacity-100 transition-opacity";

  const archiveButton = document.createElement("button");
  archiveButton.className = options.archivedView ? "text-primary hover:underline font-label-sm" : "text-outline hover:text-primary";
  archiveButton.type = "button";
  archiveButton.title = options.archivedView ? "Unarchive" : "Archive";
  archiveButton.setAttribute("aria-label", archiveButton.title);
  archiveButton.textContent = options.archivedView ? "Unarchive" : "";
  if (!options.archivedView) archiveButton.append(icon("archive"));
  archiveButton.addEventListener("click", () => updateTask(task.id, { archived: !task.archived }));

  const editButton = document.createElement("button");
  editButton.className = "text-outline hover:text-primary";
  editButton.type = "button";
  editButton.title = "Edit";
  editButton.setAttribute("aria-label", "Edit");
  editButton.append(icon("edit"));
  editButton.addEventListener("click", () => openEditTask(task));

  const deleteButton = document.createElement("button");
  deleteButton.className = "text-outline hover:text-error";
  deleteButton.type = "button";
  deleteButton.title = "Delete";
  deleteButton.setAttribute("aria-label", "Delete");
  deleteButton.append(icon("delete"));
  deleteButton.addEventListener("click", () => deleteTask(task.id));

  actions.append(editButton, archiveButton, deleteButton);
  item.append(checkbox, content, actions);
  return item;
}

async function updateTask(taskId, updates) {
  try {
    const response = await fetch(`${API_BASE}/api/tasks/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || "Could not update task");
    }

    await loadTasks({ quiet: true });
  } catch (error) {
    showError(error.message);
  }
}

async function deleteTask(taskId) {
  try {
    const response = await fetch(`${API_BASE}/api/tasks/${taskId}`, { method: "DELETE" });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || "Could not delete task");
    }

    showToast("Item deleted");
    await loadTasks({ quiet: true });
  } catch (error) {
    showError(error.message);
  }
}

function initializeTimeOptions() {
  populateTimeSelect(elements.timeInput);
  renderReviewPickers();
}

function populateTimeSelect(select) {
  const selectedValue = select.value;
  select.innerHTML = "";
  select.append(timeOption("", "Select time"), timeOption(NO_TIME_VALUE, "No time"));

  for (let minutes = 0; minutes < 24 * 60; minutes += 15) {
    const hour = Math.floor(minutes / 60);
    const minute = minutes % 60;
    const value = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
    select.append(timeOption(value, value));
  }

  if (selectedValue) setTimeSelectValue(selectedValue, select);
}

function timeOption(value, label) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  return option;
}

function setTimeSelectValue(value, select = elements.timeInput) {
  if (value && !select.querySelector(`option[value="${CSS.escape(value)}"]`)) {
    select.append(timeOption(value, value));
  }
  select.value = value || "";
  if (select === elements.timeInput) renderReviewPickers();
}

function timeValueFromTask(task) {
  if (task.time) return task.time;
  if (task.time_mode === "none" || task.all_day) return NO_TIME_VALUE;
  return "";
}

function durationValueFromTask(task) {
  if (task.all_day) return ALL_DAY_DURATION_VALUE;
  return durationHoursToMinutes(task.duration);
}

function timeModeFromReview() {
  if (elements.timeInput.value === NO_TIME_VALUE) return "none";
  return elements.timeInput.value ? "timed" : null;
}

function updateDurationOptionsForTime() {
  const hasNoTime = elements.timeInput.value === NO_TIME_VALUE;

  for (const option of elements.durationInput.options) {
    const isNoDuration = option.value === "";
    const isTimedDuration = !isNoDuration && option.value !== ALL_DAY_DURATION_VALUE;
    option.disabled = hasNoTime && isTimedDuration;
    option.hidden = option.disabled;
  }

  if (hasNoTime && !["", ALL_DAY_DURATION_VALUE].includes(elements.durationInput.value)) {
    elements.durationInput.value = "";
  }
  renderReviewPickers();
}

function handleReviewPickerClick(event) {
  const button = event.target.closest("button");
  if (!button || !elements.reviewPanel.contains(button) || button.disabled) return;

  if (button.dataset.timePeriod) {
    setReviewTimePart({ period: button.dataset.timePeriod });
    return;
  }

  if (button.dataset.timeHour) {
    setReviewTimePart({ hour: Number(button.dataset.timeHour) });
    return;
  }

  if (button.dataset.timeMinute) {
    setReviewTimePart({ minute: Number(button.dataset.timeMinute) });
    return;
  }

  if (button.dataset.timeSpecial === "no_time") {
    setTimeSelectValue(NO_TIME_VALUE);
    setDurationValue("");
    updateDurationOptionsForTime();
    return;
  }

  if ("durationValue" in button.dataset) {
    if (button.dataset.durationValue === ALL_DAY_DURATION_VALUE) {
      setTimeSelectValue(NO_TIME_VALUE);
    }
    setDurationValue(button.dataset.durationValue);
    updateDurationOptionsForTime();
  }
}

function setReviewTimePart(update) {
  const current = timeParts(elements.timeInput.value);
  const period = update.period || current.period;
  const hour12 = update.hour ?? current.hour12;
  const minute = update.minute ?? current.minute;
  const hour24 = period === "PM" ? (hour12 % 12) + 12 : hour12 % 12;
  setTimeSelectValue(`${String(hour24).padStart(2, "0")}:${String(minute).padStart(2, "0")}`);
  if (elements.durationInput.value === ALL_DAY_DURATION_VALUE) {
    elements.durationInput.value = "";
  }
  updateDurationOptionsForTime();
}

function timeParts(value) {
  if (!value || value === NO_TIME_VALUE) return { hour12: 9, minute: 0, period: "AM" };
  const [rawHour, rawMinute] = String(value).split(":").map(Number);
  const hour = Number.isFinite(rawHour) ? rawHour : 9;
  const minute = Number.isFinite(rawMinute) ? rawMinute : 0;
  return {
    hour12: hour % 12 || 12,
    minute,
    period: hour >= 12 ? "PM" : "AM",
  };
}

function setDurationValue(value) {
  if (value && !elements.durationInput.querySelector(`option[value="${CSS.escape(value)}"]`)) {
    elements.durationInput.append(timeOption(value, formatMinutesLabel(value)));
  }
  elements.durationInput.value = value;
  if (elements.durationSlider && value && value !== ALL_DAY_DURATION_VALUE) {
    elements.durationSlider.value = value;
  }
  renderReviewPickers();
}

function renderReviewPickers() {
  if (!elements.timeInput || !elements.durationInput) return;

  const timeValue = elements.timeInput.value;
  const selectedParts = timeParts(timeValue);
  const noTimeSelected = timeValue === NO_TIME_VALUE;
  const durationValue = elements.durationInput.value;

  if (elements.timePickerReadout) {
    elements.timePickerReadout.textContent = noTimeSelected
      ? "No time"
      : timeValue || "Select time";
  }

  elements.reviewPanel?.querySelectorAll("[data-time-period]").forEach((button) => {
    button.classList.toggle("is-active", !noTimeSelected && button.dataset.timePeriod === selectedParts.period);
  });

  elements.reviewPanel?.querySelectorAll("[data-time-hour]").forEach((button) => {
    button.classList.toggle("is-active", !noTimeSelected && Number(button.dataset.timeHour) === selectedParts.hour12);
  });

  elements.reviewPanel?.querySelectorAll("[data-time-minute]").forEach((button) => {
    button.classList.toggle("is-active", !noTimeSelected && Number(button.dataset.timeMinute) === selectedParts.minute);
  });

  elements.reviewPanel?.querySelectorAll("[data-time-special='no_time']").forEach((button) => {
    button.classList.toggle("is-active", noTimeSelected);
  });

  elements.reviewPanel?.querySelectorAll("[data-duration-value]").forEach((button) => {
    const isNoDuration = button.dataset.durationValue === "";
    const isTimedDuration = button.dataset.durationValue && button.dataset.durationValue !== ALL_DAY_DURATION_VALUE;
    const isActive = button.dataset.durationValue === durationValue
      && (button.dataset.durationValue !== "" || !durationValue)
      && !(button.dataset.durationValue === "" && noTimeSelected && durationValue === ALL_DAY_DURATION_VALUE);
    button.classList.toggle("is-active", isActive);
    button.disabled = noTimeSelected && isTimedDuration;
    button.hidden = noTimeSelected ? !(isNoDuration || button.dataset.durationValue === ALL_DAY_DURATION_VALUE) : false;
  });

  const sliderRow = elements.durationSlider?.closest(".duration-slider-row");
  if (sliderRow) sliderRow.hidden = noTimeSelected || durationValue === ALL_DAY_DURATION_VALUE;
  if (elements.durationSlider) elements.durationSlider.disabled = noTimeSelected || durationValue === ALL_DAY_DURATION_VALUE;

  if (elements.durationPickerReadout) {
    elements.durationPickerReadout.textContent = durationValue === ALL_DAY_DURATION_VALUE
      ? "All day"
      : durationValue
        ? formatMinutesLabel(durationValue)
        : "No duration";
  }
}

function fillReviewPanel(task, questions) {
  const effectiveQuestions = questions.length > 0
    ? questions
    : (task.missing_info || []).map((field) => ({ field }));

  elements.titleInput.value = task.title || "";
  elements.descriptionInput.value = task.description || "";
  elements.dateInput.value = task.date || "";
  setTimeSelectValue(timeValueFromTask(task));
  elements.durationInput.value = durationValueFromTask(task);
  updateDurationOptionsForTime();
  refreshProjectOptions(task.project);
  elements.newProjectInput.value = "";
  renderFollowUps(effectiveQuestions);
  updateMissingInfo(task.missing_info || []);
  updateReviewActions(task);
}

function renderFollowUps(questions) {
  elements.followUpFields.innerHTML = "";
  elements.followUpOpenText.value = "";
  elements.followUpSection.classList.toggle("hidden", questions.length === 0);
  elements.followUpSection.classList.toggle("flex", questions.length > 0);

  for (const question of questions) {
    const field = typeof question === "string" ? question : question.field;
    if (!field) continue;

    const wrapper = document.createElement("div");
    wrapper.className = "flex flex-col gap-1";

    const label = document.createElement("label");
    label.className = "font-label-sm text-outline uppercase";
    label.htmlFor = `follow-up-${field}`;
    label.textContent = labelForField(field);

    const input = field === "time" ? document.createElement("select") : document.createElement("input");
    input.className = "w-full bg-surface-container-lowest border border-outline-variant rounded-lg px-md py-sm focus:ring-1 focus:ring-primary";
    input.id = `follow-up-${field}`;
    input.name = field;

    if (field === "time") {
      populateTimeSelect(input);
    } else {
      input.type = field === "duration" ? "number" : field === "date" ? "date" : "text";
      input.step = field === "duration" ? "0.25" : "";
      input.placeholder = placeholderForField(field);
    }

    wrapper.append(label, input);
    elements.followUpFields.append(wrapper);
  }
}

function taskFromReview() {
  const timeMode = timeModeFromReview();
  const allDay = timeMode === "none" && elements.durationInput.value === ALL_DAY_DURATION_VALUE;
  const task = {
    ...(pendingTask || {}),
    ...editableMetadataFromReview(),
    title: elements.titleInput.value.trim(),
    description: elements.descriptionInput.value.trim(),
    date: elements.dateInput.value || null,
    time: timeMode === "timed" ? elements.timeInput.value : null,
    time_mode: timeMode,
    duration: allDay ? null : durationMinutesToHours(elements.durationInput.value),
    all_day: allDay,
    completed: Boolean(pendingTask?.completed),
    archived: Boolean(pendingTask?.archived),
  };

  task.missing_info = computeMissingInfo(task);
  task.follow_up_questions = task.missing_info.map((field) => ({ field }));
  return task;
}

function computeMissingInfo(task) {
  const missing = [];
  if (task.date && !task.time && task.time_mode !== "none") missing.push("time");
  if (task.time && !task.date) missing.push("date");
  return missing;
}

function setEntryMode(mode) {
  entryMode = mode;
  const isAuto = mode === "auto";

  elements.autoModeButton.classList.toggle("bg-primary", isAuto);
  elements.autoModeButton.classList.toggle("text-on-primary", isAuto);
  elements.autoModeButton.classList.toggle("text-on-surface-variant", !isAuto);
  elements.manualModeButton.classList.toggle("bg-primary", !isAuto);
  elements.manualModeButton.classList.toggle("text-on-primary", !isAuto);
  elements.manualModeButton.classList.toggle("text-on-surface-variant", isAuto);

  elements.taskInput.placeholder = isAuto
    ? "Type a goal like 'send proposal tomorrow' or an event like 'Dinner at 7pm for 2 hours'..."
    : "Type the goal or event name, then fill the fields below...";
  elements.parseButtonLabel.textContent = isAuto ? "Parse" : "Add Manually";
}

function openManualTask() {
  const note = elements.taskInput.value.trim();
  pendingEntryMode = "manual";
  pendingTask = normalizeTask({
    title: note,
    description: "",
    date: null,
    time: null,
    time_mode: null,
    duration: null,
    all_day: false,
    completed: false,
    archived: false,
    project: "project",
    missing_info: [],
    follow_up_questions: [],
  });

  fillReviewPanel(pendingTask, []);
  elements.reviewPanel.classList.remove("hidden");
  elements.reviewPanel.classList.add("flex");
}

function openEditTask(task) {
  pendingEntryMode = "edit";
  pendingTask = normalizeTask(task);
  fillReviewPanel(pendingTask, pendingTask.follow_up_questions || []);
  elements.reviewPanel.classList.remove("hidden");
  elements.reviewPanel.classList.add("flex");
  elements.reviewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function updateReviewActions(task) {
  const isEditing = Boolean(task.id);
  elements.applyDetailsButton.textContent = isEditing ? "Delete" : "Apply Details";
  elements.applyDetailsButton.classList.toggle("bg-error-container", isEditing);
  elements.applyDetailsButton.classList.toggle("text-on-error-container", isEditing);
  elements.applyDetailsButton.classList.toggle("hover:bg-outline", !isEditing);
  elements.applyDetailsButton.classList.toggle("bg-outline-variant", !isEditing);
  elements.applyDetailsButton.classList.toggle("text-on-surface-variant", !isEditing);
}

function editableMetadataFromReview() {
  const newProject = elements.newProjectInput.value.trim();
  const project = newProject || elements.projectInput.value.trim();
  return { project: project || "project" };
}

function collectFollowUpAnswers(missingFields = []) {
  const answers = {};

  for (const input of elements.followUpFields.querySelectorAll("input")) {
    if (!input.value.trim()) continue;
    if (input.name === "duration") {
      answers[input.name] = input.value.trim();
    } else {
      answers[input.name] = input.value.trim();
    }
  }

  const openText = elements.followUpOpenText.value.trim();
  if (openText) {
    for (const field of missingFields) {
      if (answers[field]) continue;
      if (field === "duration") {
        const duration = parseDurationClarification(openText);
        if (duration != null) answers[field] = String(duration);
      } else {
        answers[field] = openText;
      }
    }
  }

  return answers;
}

function normalizeTask(task) {
  const normalized = {
    id: task.id,
    user_id: task.user_id || currentUserId,
    title: task.title || "",
    description: task.description || "",
    date: task.date || null,
    time: task.time || null,
    time_mode: task.time_mode || (task.time ? "timed" : null),
    duration: task.duration ?? null,
    all_day: Boolean(task.all_day),
    completed: Boolean(task.completed),
    archived: Boolean(task.archived),
    project: cleanProject(task.project) || "project",
    missing_info: [],
    follow_up_questions: [],
  };
  normalized.missing_info = computeMissingInfo(normalized);
  normalized.follow_up_questions = normalized.missing_info.map((field) => ({ field }));
  return normalized;
}

function taskPatchPayload(task) {
  return {
    title: task.title,
    description: task.description,
    date: task.date,
    time: task.time,
    time_mode: task.time_mode,
    duration: task.duration,
    all_day: task.all_day,
    completed: task.completed,
    archived: task.archived,
    project: task.project,
  };
}

function cleanProject(project) {
  if (project == null) return null;
  const value = String(project).trim();
  return value || null;
}

function refreshProjectOptions(selectedProject = null) {
  const projectNames = new Set(
    tasks
      .map((task) => cleanProject(task.project))
      .filter(Boolean),
  );
  const selected = cleanProject(selectedProject);
  if (selected) projectNames.add(selected);

  elements.projectInput.innerHTML = "";

  const emptyOption = document.createElement("option");
  emptyOption.value = "project";
  emptyOption.textContent = "project";
  elements.projectInput.append(emptyOption);

  for (const project of [...projectNames].sort((a, b) => a.localeCompare(b))) {
    const option = document.createElement("option");
    option.value = project;
    option.textContent = project;
    elements.projectInput.append(option);
  }

  elements.projectInput.value = selected || "";
  syncProjectColorInput();
}

function loadProjectColors() {
  try {
    return JSON.parse(localStorage.getItem(PROJECT_COLORS_KEY)) || {};
  } catch {
    return {};
  }
}

function saveProjectColor(project, color) {
  const clean = cleanProject(project) || "project";
  projectColors[clean] = color || DEFAULT_PROJECT_COLOR;
  localStorage.setItem(PROJECT_COLORS_KEY, JSON.stringify(projectColors));
}

function projectColor(project) {
  const clean = cleanProject(project) || "project";
  return projectColors[clean] || DEFAULT_PROJECT_COLOR;
}

function projectTint(project) {
  return `${projectColor(project)}18`;
}

function syncProjectColorInput() {
  const project = elements.newProjectInput.value.trim() || elements.projectInput.value || "project";
  elements.projectColorInput.value = projectColor(project);
}

function parseDurationClarification(text) {
  const normalized = text.toLowerCase();
  const numericMatch = normalized.match(/(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|m|min|mins|minute|minutes)?/);
  if (numericMatch) {
    const value = Number(numericMatch[1]);
    const unit = numericMatch[2] || "hour";
    if (!Number.isFinite(value) || value <= 0) return null;
    return unit.startsWith("m") ? value / 60 : value;
  }

  const wordDurations = {
    "quarter hour": 0.25,
    "half hour": 0.5,
    "one hour": 1,
    "two hours": 2,
    "three hours": 3,
  };

  for (const [phrase, hours] of Object.entries(wordDurations)) {
    if (normalized.includes(phrase)) return hours;
  }

  return null;
}

function updateMissingInfo(missingInfo) {
  if (missingInfo.length === 0) {
    elements.missingInfo.classList.add("hidden");
    elements.missingInfo.textContent = "";
    return;
  }
  elements.missingInfo.textContent = `Missing: ${missingInfo.join(", ")}`;
  elements.missingInfo.classList.remove("hidden");
}

function switchView(viewName) {
  activeView = viewName;
  closeMobileMenu();

  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === viewName);
  });

  document.querySelectorAll(".view-section").forEach((section) => {
    section.classList.toggle("active", section.id === `view-${viewName}`);
  });
}

function resetPendingTask() {
  pendingTask = null;
  pendingEntryMode = entryMode;
  elements.followUpFields.innerHTML = "";
  elements.reviewPanel.classList.add("hidden");
  elements.reviewPanel.classList.remove("flex");
  updateReviewActions({});
  updateMissingInfo([]);
}

function missingManualFields(task) {
  const labels = {
    title: "title",
    description: "description",
  };

  return Object.entries(labels)
    .filter(([field]) => task[field] == null || task[field] === "")
    .map(([, label]) => label);
}

function setBusy(isBusy, message = "Parsing your task...") {
  elements.parseButton.disabled = isBusy;
  elements.applyDetailsButton.disabled = isBusy;
  elements.confirmButton.disabled = isBusy;
  elements.loadingMessage.textContent = message;
  elements.loadingOverlay.classList.toggle("hidden", !isBusy);
  elements.loadingOverlay.classList.toggle("flex", isBusy);
}

function setSyncDisabled(isDisabled) {
  if (elements.syncButton) elements.syncButton.disabled = isDisabled;
  if (elements.mobileSyncButton) elements.mobileSyncButton.disabled = isDisabled;
}

function showError(message) {
  elements.errorMessage.textContent = message;
  elements.errorArea.classList.remove("hidden");
  window.setTimeout(clearError, 4500);
}

function clearError() {
  elements.errorArea.classList.add("hidden");
  elements.errorMessage.textContent = "";
}

function showToast(message) {
  const toast = document.createElement("div");
  toast.className = "bg-inverse-surface text-inverse-on-surface px-md py-sm rounded-lg shadow-md font-body-md";
  toast.textContent = message;
  elements.toastRegion.append(toast);
  window.setTimeout(() => toast.remove(), 3000);
}

function toggleEmpty(element, isEmpty) {
  element.classList.toggle("hidden", !isEmpty);
}

function formatMeta(task) {
  const parts = [];
  if (task.date) parts.push({ icon: "calendar_today", text: task.date });
  if (task.time) parts.push({ icon: "schedule", text: task.time });
  if (task.all_day) parts.push({ icon: "event", text: "All day" });
  if (task.duration) parts.push({ icon: "timer", text: formatDuration(task.duration) });
  return parts;
}

function formatDuration(hours) {
  const minutes = Math.round(Number(hours) * 60);
  if (!Number.isFinite(minutes) || minutes <= 0) return "";
  if (minutes % 60 === 0) return `${minutes / 60}h`;
  if (minutes > 60) return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  return `${minutes}m`;
}

function formatMinutesLabel(minutes) {
  const value = Number(minutes);
  if (!Number.isFinite(value) || value <= 0) return "No duration";
  if (value % 60 === 0) return `${value / 60}h`;
  if (value > 60) return `${Math.floor(value / 60)}h ${value % 60}m`;
  return `${value}m`;
}

function durationHoursToMinutes(hours) {
  if (hours == null || hours === "") return "";
  const minutes = Math.round(Number(hours) * 60);
  return Number.isFinite(minutes) ? String(minutes) : "";
}

function durationMinutesToHours(minutes) {
  if (!minutes) return null;
  const value = Number(minutes);
  if (!Number.isFinite(value) || value <= 0) return null;
  return value / 60;
}

function icon(name) {
  const span = document.createElement("span");
  span.className = "material-symbols-outlined text-[14px]";
  span.textContent = name;
  return span;
}

function labelForField(field) {
  const labels = {
    date: "Date",
    time: "Time",
    duration: "Duration in hours",
  };
  return labels[field] || field;
}

function placeholderForField(field) {
  const placeholders = {
    date: "2026-05-12",
    time: "14:00",
    duration: "1",
  };
  return placeholders[field] || "";
}

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;

  try {
    await navigator.serviceWorker.register("/sw.js");
  } catch (error) {
    console.debug("Service worker registration failed", error);
  }
}
