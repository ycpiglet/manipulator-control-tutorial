from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.course_progress import course_milestone_summary  # noqa: E402


class CourseProgressTests(unittest.TestCase):
    def test_course_milestone_summary_groups_learning_path_steps(self) -> None:
        self.assertEqual(
            course_milestone_summary(()),
            "Milestones: 1D Dynamics 0/2; PID Control 0/2; 2DOF Control 0/3; "
            "Panda Manipulation 0/3; Course Compare 0/1. Next milestone: 1D Dynamics.",
        )
        self.assertEqual(
            course_milestone_summary((True, True, True, False, False, False, False, False, False, False, False)),
            "Milestones: 1D Dynamics 2/2; PID Control 1/2; 2DOF Control 0/3; "
            "Panda Manipulation 0/3; Course Compare 0/1. Next milestone: PID Control.",
        )
        self.assertEqual(
            course_milestone_summary((True,) * 11),
            "Milestones: 1D Dynamics 2/2; PID Control 2/2; 2DOF Control 3/3; "
            "Panda Manipulation 3/3; Course Compare 1/1. All milestones ready for review.",
        )


if __name__ == "__main__":
    unittest.main()
