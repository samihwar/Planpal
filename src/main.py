from storage import load_tasks

def main():
    tasks = load_tasks()
    print("Loaded tasks:", tasks)

if __name__ == "__main__":
    main()