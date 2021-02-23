import os
import json
from pprint import pprint
from utils import compute_score
import multiprocessing
import time


PATCH_CATEGORY_QUALITY_DICT ={
    'PatchCategory.NegFix': "BAD",
    'PatchCategory.NoneFix': "None", 
    '': "BAD", # is only including pf
    'PatchCategory.NoisyFixPartial': "GOOD",
    'PatchCategory.NoisyFixFull': "GOOD",
    'PatchCategory.CleanFixPartial': "GOOD",
    'PatchCategory.CleanFixFull': "GOOD",
}


class PatchRerankerSamApproach:
    def __init__(
        self,
        data_dir,
        output_dir,
        formula="Ochiai",
        matrix_type="partial",
        modified_entity_level="method",
        num_threads=6,
    ):
        self._data_dir = data_dir

        self._formula = formula
        self._matrix_type = matrix_type
        self._modified_entity_level = modified_entity_level
        self._num_threads = num_threads

        output_dir = output_dir + "_{}".format(modified_entity_level)
        self._output_dir = os.path.join(output_dir, self._matrix_type)

        os.makedirs(self._output_dir, exist_ok=True)
        self.project_version_tuple_list = []
    

    def clean_data(self, pactch_data):
        problematic_id_list = []

        for patch_id, pactch_content in pactch_data.items():
            if len(pactch_content["patch_category"]) == 0:
                problematic_id_list.append(patch_id)
        
        for patch_id in problematic_id_list:
            pactch_data.pop(patch_id)
   

    def change_repair_data_level(self, repair_data):
        if self._modified_entity_level == "method":
            return

        if self._modified_entity_level in ["class", "package"]:
            modified_entity_id_mapping = {}
            method_map = repair_data["method"]
            org_new_id_mapping = {}

            for id, method in method_map.items():
                clazz = method.split(":")[0]
                pkg = ".".join(clazz.split(".")[:-1])

                if self._modified_entity_level == "class":
                    entity = clazz

                if self._modified_entity_level == "package":
                    entity = pkg
                
                if entity not in modified_entity_id_mapping:
                    modified_entity_id_mapping[entity] = len(modified_entity_id_mapping.keys())
                
                org_new_id_mapping[id] = modified_entity_id_mapping[entity]
            
            for patch_id, patch_data in repair_data["patch"].items():
                patch_data["method"] = org_new_id_mapping[str(patch_data["method"])]
        
        if self._modified_entity_level == "statement":
            modified_entity_id_mapping = {}

            for patch_id, patch_data in repair_data["patch"].items():
                statement = str(patch_data["method"]) + "_" + str(patch_data["line"])

                if statement not in modified_entity_id_mapping:
                    modified_entity_id_mapping[statement] = len(modified_entity_id_mapping.keys())

                statement_id = modified_entity_id_mapping[statement]
                patch_data["method"] = statement_id


    def _revise_version_data(self, version_data):
        revised_subject_patch_dict = {}

        for patch_id, patch_data in version_data.items():
            patch_id = int(patch_id)

            revised_subject_patch_dict[patch_id] = {
                "modified_method": patch_data["method"],
                "true_positive": 1,
                "false_positive": 1,
                "true_negative": 1,
                "false_negative": 1,
                "priority": 0.0,
                "validated": False,
                "patch_category": patch_data["patch_category"],
                "init_priority": 0.0,
            }
        
        return revised_subject_patch_dict
    

    def get_all_project_version_tuple(self):
        data_path = os.path.join(self._data_dir, self._matrix_type)
        word_list = [i.replace(".json", "") for i in os.listdir(data_path) if i.endswith(".json")]
        for i in word_list:
            proj, version_str = i.split("_")
            self.project_version_tuple_list.append((proj, int(version_str)))


    def _get_validation_candidate(self, revised_version_data):
        id_list = sorted(list(revised_version_data.keys()))
        selected_candidate_id = -1
        for id in id_list:
            if not revised_version_data[id]["validated"]:
                # init
                if selected_candidate_id == -1:
                    selected_candidate_id = id
                
                cur_candidate_priority = revised_version_data[id]["priority"]
                selected_candidate_priority = revised_version_data[selected_candidate_id]["priority"]

                if cur_candidate_priority > selected_candidate_priority:
                    selected_candidate_id = id
        
        return selected_candidate_id
    

    def _update_subject_patch(self, revised_subject_patch_dict, selected_candidate_id):
        # patch_category relates to priority
        selected_modified_method = revised_subject_patch_dict[selected_candidate_id]["modified_method"]
        selected_patch_quality = PATCH_CATEGORY_QUALITY_DICT[
            revised_subject_patch_dict[selected_candidate_id]["patch_category"]
        ]

        revised_subject_patch_dict[selected_candidate_id]["validated"] = True
        # modified_method: computed_score
        cached_result = {}

        for id, patch_data in revised_subject_patch_dict.items():
            if not revised_subject_patch_dict[id]["validated"]:
                cur_modified_method = revised_subject_patch_dict[id]["modified_method"]
                if cur_modified_method == selected_modified_method:
                    num_match, num_diff = [1, 0]
                else:
                    num_match, num_diff = [0, 1]

                if selected_patch_quality == "GOOD":
                    revised_subject_patch_dict[id]["true_positive"] += num_match
                    revised_subject_patch_dict[id]["false_positive"] += num_diff

                if selected_patch_quality == "BAD":
                    revised_subject_patch_dict[id]["true_negative"] += num_match
                    revised_subject_patch_dict[id]["false_negative"] += num_diff

                if cur_modified_method not in cached_result:
                    computed_score = compute_score(
                        revised_subject_patch_dict[id]["true_positive"],
                        revised_subject_patch_dict[id]["false_positive"],
                        revised_subject_patch_dict[id]["true_negative"],
                        revised_subject_patch_dict[id]["false_negative"],
                        self._formula
                    )
                    cached_result[cur_modified_method] = computed_score
                else:
                    computed_score = cached_result[cur_modified_method]

                revised_subject_patch_dict[id]["priority"] = (
                    revised_subject_patch_dict[id]["init_priority"] + computed_score
                )


    def _compute_baseline(self, revised_subject_patch_dict):
        id_list = sorted(list(revised_subject_patch_dict.keys()))
        cnt = 0
        for id in id_list:
            cnt += 1
            if revised_subject_patch_dict[id]["patch_category"] == "PatchCategory.CleanFixFull":
                return cnt


    def doesIncludePlausibleFix(self, version_data):
        for patch_id, patch_data in version_data.items():
            if patch_data["patch_category"] == "PatchCategory.CleanFixFull":
                return True
        
        return False


    def jit_patch_rerank(self, project_version_tuple):
        project, version = project_version_tuple
        print("processing {} - {} - {}".format(project, version, self._matrix_type))

        json_file = os.path.join(self._data_dir, self._matrix_type, "{}_{}.json".format(project, version))
        with open(json_file) as file:
            repair_data = json.load(file)

        result = {}
        version_data = repair_data["patch"]

        if not self.doesIncludePlausibleFix(version_data):
            return
        
        self.change_repair_data_level(repair_data)

        revised_subject_patch_dict = self._revise_version_data(version_data)
        baseline_rank = self._compute_baseline(revised_subject_patch_dict)

        visited_patch_id_list = []
        selected_candidate_id = self._get_validation_candidate(revised_subject_patch_dict)
        self._update_subject_patch(revised_subject_patch_dict, selected_candidate_id)

        selected_candidate_patch_category = revised_subject_patch_dict[selected_candidate_id]["patch_category"]
        visited_patch_id_list.append(selected_candidate_id)

        while selected_candidate_patch_category != "PatchCategory.CleanFixFull":
            selected_candidate_id = self._get_validation_candidate(revised_subject_patch_dict)
            if selected_candidate_id != -1:
                visited_patch_id_list.append(selected_candidate_id)
            else:
                assert len(visited_patch_id_list) == len(revised_subject_patch_dict.keys()), "error for checked all patches"
                break

            self._update_subject_patch(revised_subject_patch_dict, selected_candidate_id)
            selected_candidate_patch_category = revised_subject_patch_dict[selected_candidate_id]["patch_category"]

        num_trials = len(visited_patch_id_list)

        result = {
            "gt": baseline_rank,
            "eval": num_trials,
            "visited_patch_id_list": visited_patch_id_list,
        }

        output_filename = os.path.join(self._output_dir, "{}_{}.json".format(project, version))
        with open(output_filename, 'w') as json_file:
            json.dump(result, json_file, indent=4)
        

    def run_all(self):
        self.get_all_project_version_tuple()
        pool = multiprocessing.Pool(processes=self._num_threads)
        pool.map(self.jit_patch_rerank, self.project_version_tuple_list)
        print(self._output_dir)


if __name__ == "__main__":
    data_dir = os.path.abspath("/filesystem/patch_ranking/ProflPartialMatrix/python/data/prapr/yiling_data/output")
    output_dir = os.path.abspath("eval")

    for matrix_type_i in ["partial", "full"]:
        for modified_entity_level_i in ["class", "package", "method", "statement"]:
            start_time = time.time()
            pr = PatchRerankerSamApproach(
                data_dir,
                output_dir,
                formula="Ochiai",
                matrix_type=matrix_type_i,
                modified_entity_level=modified_entity_level_i,
                num_threads=8,
            )
            pr.run_all()
            print("--- {} mins ---".format((time.time() - start_time) / 60.0))
