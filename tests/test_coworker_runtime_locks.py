import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.coworker_runtime.locks import acquire_locks, release_task_locks  # noqa: E402


class TestCoworkerRuntimeLocks(unittest.TestCase):
    def test_locks_block_overlapping_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            locks_dir = Path(tmp) / "locks"
            root = Path(tmp) / "root"
            root.mkdir()
            target = root / "file.txt"
            target.write_text("x", encoding="utf-8")

            dir_handle = acquire_locks(
                [root],
                locks_dir=locks_dir,
                task_id="task-dir",
                owner="worker-1",
            )
            self.assertTrue(dir_handle.lock_files)

            file_blocked = acquire_locks(
                [target],
                locks_dir=locks_dir,
                task_id="task-file",
                owner="worker-2",
            )
            self.assertFalse(file_blocked.lock_files)

            dir_handle.release()

            file_handle = acquire_locks(
                [target],
                locks_dir=locks_dir,
                task_id="task-file",
                owner="worker-2",
            )
            self.assertTrue(file_handle.lock_files)

            dir_blocked = acquire_locks(
                [root],
                locks_dir=locks_dir,
                task_id="task-dir-2",
                owner="worker-3",
            )
            self.assertFalse(dir_blocked.lock_files)

            file_handle.release()

    def test_locks_block_other_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            locks_dir = Path(tmp) / "locks"
            target = Path(tmp) / "file.txt"
            target.write_text("x", encoding="utf-8")

            handle = acquire_locks(
                [target],
                locks_dir=locks_dir,
                task_id="task-one",
                owner="worker-1",
            )
            self.assertTrue(handle.lock_files)

            blocked = acquire_locks(
                [target],
                locks_dir=locks_dir,
                task_id="task-two",
                owner="worker-2",
            )
            self.assertFalse(blocked.lock_files)

            same_task = acquire_locks(
                [target],
                locks_dir=locks_dir,
                task_id="task-one",
                owner="worker-1",
            )
            self.assertTrue(same_task.lock_files)

            handle.release()
            same_task.release()

            reopened = acquire_locks(
                [target],
                locks_dir=locks_dir,
                task_id="task-three",
                owner="worker-3",
            )
            self.assertTrue(reopened.lock_files)
            release_task_locks([target], locks_dir=locks_dir, task_id="task-three")


if __name__ == "__main__":
    unittest.main()
