"""
Code for creating on-the-fly random file pairings.
"""
import pandas as pd
import numpy as np
import itertools


class PairGen:
    def __init__(self, dataframe, crop_length, match_rate=.5,
                 samples_per_epoch=1000):
        self.dataframe = dataframe
        self.crop_length = crop_length
        self.match_rate = match_rate
        self.samples_per_epoch = samples_per_epoch

        self.rng = np.random.default_rng(1)

        self.num_files = len(dataframe)

        # Mapping from author names to file index
        self.files_by_auth_name = dataframe.groupby(['username']).indices

        # reverse file to author mapping
        self.indx_to_auth = {}
        for item in self.files_by_auth_name.items():
            for indx in item[1]:
                self.indx_to_auth[indx] = item[0]

        # Store all of the files by authors with more than one file.
        self.files_with_pairs = np.array(list(itertools.chain.from_iterable(
            filter(
                lambda x:
                len(x) > 1,
                self.files_by_auth_name.values()))))

    def gen(self):
        """
        Generate file pairings where each file is equally likely to be
        included in a pairing.

         Algorithm:
        randomly determine if matching
        if matching:
           Randomly select a file from files_with_pairs
           map to the author of that file
           randomly select a pair of authors by that author.  (The initial file
           that was selected may not be in the pair)
        if not matching
           while pair is by the same author
              select a pair of files


        """
        for _ in range(self.samples_per_epoch):
            matching_pair = self.rng.random() < self.match_rate
            if matching_pair:
                rand_file = self.rng.choice(self.files_with_pairs, 1,
                                            shuffle=False)[0]
                rand_auth = self.indx_to_auth[rand_file]

                rand_pair = self.rng.choice(self.files_by_auth_name[rand_auth],
                                            2, replace=False, shuffle=False)

            else:
                rand_pair = self.rng.choice(self.num_files, 2, replace=False,
                                            shuffle=False)
                while (self.indx_to_auth[rand_pair[0]] ==
                       self.indx_to_auth[rand_pair[1]]):
                    rand_pair = self.rng.choice(self.num_files, 2,
                                                replace=False, shuffle=False)

            yield ({'input_1': self.random_crop(rand_pair[0], self.crop_length),
                    'input_2': self.random_crop(rand_pair[1],
                                                self.crop_length)},
                   matching_pair)

    def random_crop(self, file_indx, crop_length):
        """
        Return a random crop from the file at the provided index. If
        crop_length is longer than the length of the file, then the entire
        file will be returned.
        """

        contents = self.dataframe['file_content'][file_indx]
        if len(contents) > crop_length:
            start = self.rng.integers(0, len(contents) - crop_length + 1)
            contents = contents[start:start + crop_length]
        return contents.ljust(crop_length, '\0')


if __name__ == "__main__":
    import time

    df = pd.read_hdf('/home/spragunr/nobackup/gcj_java_test.h5')
    pg = PairGen(df, crop_length=1200, samples_per_epoch=10000)

    start_time = time.perf_counter()
    for _ in range(2):
        for pair in pg.gen():
            # print(".", end="")
            pass

    print("Execution time:", time.perf_counter() - start_time)
