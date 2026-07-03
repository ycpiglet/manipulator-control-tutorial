from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mclab.course_progress import course_milestone_label_for_step_index, course_milestone_summary  # noqa: E402


class CourseProgressTests(unittest.TestCase):
    def test_course_milestone_summary_groups_learning_path_steps(self) -> None:
        self.assertEqual(
            course_milestone_summary(()),
            "Milestones: 1D Dynamics 0/2; PID Control 0/2; 2DOF Control 0/4; "
            "Panda Manipulation 0/3; Course Compare 0/1. Next milestone: 1D Dynamics.",
        )
        self.assertEqual(
            course_milestone_summary((True, True, True, False, False, False, False, False, False, False, False, False)),
            "Milestones: 1D Dynamics 2/2; PID Control 1/2; 2DOF Control 0/4; "
            "Panda Manipulation 0/3; Course Compare 0/1. Next milestone: PID Control.",
        )
        self.assertEqual(
            course_milestone_summary((True,) * 12),
            "Milestones: 1D Dynamics 2/2; PID Control 2/2; 2DOF Control 4/4; "
            "Panda Manipulation 3/3; Course Compare 1/1. All milestones ready for review.",
        )

    def test_course_milestone_label_for_step_index_names_course_position(self) -> None:
        self.assertEqual(course_milestone_label_for_step_index(-1), "")
        self.assertEqual(course_milestone_label_for_step_index(0), "1D Dynamics")
        self.assertEqual(course_milestone_label_for_step_index(3), "PID Control")
        self.assertEqual(course_milestone_label_for_step_index(6), "2DOF Control")
        self.assertEqual(course_milestone_label_for_step_index(9), "Panda Manipulation")
        self.assertEqual(course_milestone_label_for_step_index(11), "Course Compare")
        self.assertEqual(course_milestone_label_for_step_index(12), "Extra")


if __name__ == "__main__":
    unittest.main()
