// DOM Elements
const taskInput = document.getElementById('taskInput');
const dateInput = document.getElementById('dateInput');
const addTaskBtn = document.getElementById('addTaskBtn');
const taskList = document.getElementById('taskList');
const taskCount = document.getElementById('taskCount');
const emptyState = document.getElementById('emptyState');

// Tasks array
let tasks = [];

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    loadTasks();
    renderTasks();
    updateTaskCount();
});

// Event Listeners
addTaskBtn.addEventListener('click', addTask);
taskInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        addTask();
    }
});

// Add new task
function addTask() {
    const taskText = taskInput.value.trim();

    if (taskText === '') {
        return;
    }

    const task = {
        id: Date.now(),
        text: taskText,
        date: dateInput.value || null,
        completed: false
    };

    tasks.push(task);
    taskInput.value = '';
    dateInput.value = '';

    saveTasks();
    renderTasks();
    updateTaskCount();
}

// Toggle task completion
function toggleTask(id) {
    const task = tasks.find(t => t.id === id);
    if (task) {
        task.completed = !task.completed;
        saveTasks();
        renderTasks();
        updateTaskCount();
    }
}

// Delete task
function deleteTask(id) {
    tasks = tasks.filter(t => t.id !== id);
    saveTasks();
    renderTasks();
    updateTaskCount();
}

// Render all tasks
function renderTasks() {
    taskList.innerHTML = '';

    if (tasks.length === 0) {
        emptyState.classList.remove('hidden');
        return;
    }

    emptyState.classList.add('hidden');

    tasks.forEach(task => {
        const taskItem = createTaskElement(task);
        taskList.appendChild(taskItem);
    });
}

// Create task element
function createTaskElement(task) {
    const li = document.createElement('li');
    li.className = 'task-item';

    // Checkbox
    const checkbox = document.createElement('div');
    checkbox.className = `task-checkbox ${task.completed ? 'checked' : ''}`;
    checkbox.addEventListener('click', () => toggleTask(task.id));

    // Task content container
    const taskContent = document.createElement('div');
    taskContent.className = 'task-content';
    taskContent.addEventListener('click', () => toggleTask(task.id));

    // Task text
    const taskText = document.createElement('div');
    taskText.className = `task-text ${task.completed ? 'completed' : ''}`;
    taskText.textContent = task.text;

    taskContent.appendChild(taskText);

    // Task date (if exists)
    if (task.date) {
        const taskDate = document.createElement('div');
        const dateObj = new Date(task.date);
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const taskDateObj = new Date(task.date);
        taskDateObj.setHours(0, 0, 0, 0);

        let dateClass = 'task-date';
        let dateIcon = '📅';

        if (taskDateObj < today && !task.completed) {
            dateClass += ' overdue';
            dateIcon = '⚠️';
        } else if (taskDateObj.getTime() === today.getTime()) {
            dateClass += ' today';
            dateIcon = '⭐';
        }

        taskDate.className = dateClass;
        taskDate.innerHTML = `${dateIcon} ${formatDate(task.date)}`;
        taskContent.appendChild(taskDate);
    }

    // Delete button
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'delete-btn';
    deleteBtn.textContent = '×';
    deleteBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteTask(task.id);
    });

    li.appendChild(checkbox);
    li.appendChild(taskContent);
    li.appendChild(deleteBtn);

    return li;
}

// Format date for display
function formatDate(dateString) {
    const date = new Date(dateString);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const dateToCheck = new Date(dateString);
    dateToCheck.setHours(0, 0, 0, 0);

    if (dateToCheck.getTime() === today.getTime()) {
        return 'Today';
    } else if (dateToCheck.getTime() === tomorrow.getTime()) {
        return 'Tomorrow';
    } else {
        const options = { month: 'short', day: 'numeric', year: 'numeric' };
        return date.toLocaleDateString('en-US', options);
    }
}

// Update task count
function updateTaskCount() {
    const total = tasks.length;
    const completed = tasks.filter(t => t.completed).length;
    const pending = total - completed;

    if (total === 0) {
        taskCount.textContent = '0 tasks';
    } else if (pending === 0) {
        taskCount.textContent = `All ${total} tasks completed!`;
    } else {
        taskCount.textContent = `${pending} of ${total} tasks remaining`;
    }
}

// Save tasks to localStorage
function saveTasks() {
    localStorage.setItem('tasks', JSON.stringify(tasks));
}

// Load tasks from localStorage
function loadTasks() {
    const storedTasks = localStorage.getItem('tasks');
    if (storedTasks) {
        tasks = JSON.parse(storedTasks);
    }
}
