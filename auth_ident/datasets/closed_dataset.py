from os.path import join
import pandas as pd
import numpy as np
import tensorflow as tf
from time import perf_counter
import sentencepiece as spm
from auth_ident import CPP_JAVA_INDEX_BUFFER


class ClosedDataset:
    """
    Code for creating on-the-fly random file pairings.
    """
    def __init__(self,
                 crop_length,
                 max_authors,
                 k_cross_val=5,
                 data_file=None,
                 encoding_type='spm',
                 spm_model_file=None):

        if (k_cross_val < 2):
            print("k_cross_val ust be greater than 1.")
            exit(1)

        self.crop_length = crop_length
        self.k_cross_val = k_cross_val
        self.max_authors = max_authors

        self.rng = np.random.default_rng(1)

        # For one-hot
        chars_to_encode = "qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM\n\r\t " + r"1234567890-=!@#$%^&*()_+[]{}|;':\",./<>?"
        self.start = "<start>"
        self.end = "<end>"
        chars_to_encode = [self.start, self.end] + list(chars_to_encode)

        if encoding_type == "spm":
            sp = spm.SentencePieceProcessor(model_file=join("data/", spm_model_file))
            self.len_encoding = sp.vocab_size()
        elif encoding_type == "tokens":
            
            if "cpp" in data_file:
                self.len_encoding = CPP_JAVA_INDEX_BUFFER
            elif "java" in data_file:
                self.len_encoding = CPP_JAVA_INDEX_BUFFER
            else:
                assert False, "No python length encoding known"

            # Assume format data/.../{language}_{type}_encoded.h5
            top_ids_file = "data/" + "_".join(data_file.split("_")[:-2]) + "_top_identifiers.txt"
            with open(top_ids_file) as f:
                num_reserved_identifiers = sum([1 for line in f])

            self.len_encoding += num_reserved_identifiers
            print(f"ENCODING_LEN: {self.len_encoding}")
        else:
            self.len_encoding = len(chars_to_encode) + 1

        chars_index = [i for i in range(len(chars_to_encode))]

        char_map = tf.lookup.KeyValueTensorInitializer(chars_to_encode,
                                                       chars_index,
                                                       key_dtype=tf.string,
                                                       value_dtype=tf.int64)
        self.table = tf.lookup.StaticVocabularyTable(char_map,
                                                     num_oov_buckets=1)

        # Load dataframe
        f = join("data/", data_file)
        self.dataframe = pd.read_hdf(f)

        self.bos_id = 1
        self.eos_id = 2

    def get_dataset(self, return_file_indicies=False):
        return list(self.get_two(self.dataframe, return_file_indicies))

    def get_two(self, df, return_file_indicies=False):
        """
        Generate file pairings where each file is equally likely to be
        included in a pairing.

         Algorithm:
        Take all authors with >= k files
        while num_files < files_requested:
            pick i randomly from authors(with atleast k files remaining)
                crop, encode, and add k files from i to the dataset
                if i in authors_seen:
                    label = authors_seen.index(author)
                else:
                    label = len(authors_seen)
                    authors_seen.append(i)

        Algorithm 2.0:
        files = k files from all authors with >= k files
        for i in len(files)
            y[i] = author(files[i])
        """

        # TODO Make faster

        # Mapping from author names to file index
        # ["tom"] -> [1, 17, 37]
        self.files_by_auth_name = df.groupby(['username']).indices

        # Map from authors with >= k files to their files (indx)
        #  ["Larry"] -> [4, 34, 67, 231, 453, 768]
        self.authors_with_k = dict(
            filter(lambda x: len(x[1]) >= self.k_cross_val,
                   self.files_by_auth_name.items()))

        self.authors_with_k = {author: self.authors_with_k[author] for author in list(self.authors_with_k)[:self.max_authors]}

        # Modifies the map s.t. each author has exactly k files
        for k in self.authors_with_k:
            self.authors_with_k[k] = self.rng.choice(self.authors_with_k[k],
                                                     self.k_cross_val,
                                                     replace=False,
                                                     shuffle=False)

        # List of all files sorted by author where
        # each author has exactly k files
        files = np.concatenate(list(self.authors_with_k.values()))

        # Generate labels
        y = np.floor(np.arange(len(files)) / self.k_cross_val)

        # Create indices to grab one of each author in each fold
        cross_val_indicies = np.zeros(len(files), dtype=np.int32)
        # files should always be divizable by k
        print("folding")
        fold_size = int(len(files) / self.k_cross_val)
        for i in range(self.k_cross_val):
            cross_val_indicies[i * fold_size:(i + 1) * fold_size] = np.arange(
                i, len(files), self.k_cross_val)

        print("reorganizing")
        # Reorganize labels
        y = y[cross_val_indicies]

        # crop = np.vectorize(self.random_crop)
        # files = crop(files, self.crop_length, df)
        print("encoding")
        X = np.zeros([cross_val_indicies.shape[0], self.crop_length])
        print(f"len encoding: {cross_val_indicies.shape}")
        for i, cross_val_index in enumerate(cross_val_indicies):
            print(i, end="\r")
            cropped = self.crop(files[cross_val_index],
                                       self.crop_length, df)
            X[i, :cropped.shape[0] + 1] = self.add_end_tokens(cropped)
        print("finished dataset")

        print(f"num_authors {len(self.authors_with_k)}")

        if return_file_indicies:
            return X, y, files
        else:
            return X, y

    def crop(self, file_indx, crop_length, df):
        """
        Return a crop from the file at the provided index. If
        crop_length is longer than the length of the file, then the entire
        file will be returned.
        """
        contents = np.array(df['file_content'][file_indx])
        # Minus two to account for bos and eso tokens
        max_crop = min(len(contents), crop_length) - 1
        cropped_contents = contents[:max_crop]

        return cropped_contents

    def add_end_tokens(self, cropped_contents):
        cropped_contents[-1] = self.eos_id
        cropped_contents = np.insert(cropped_contents, 0, self.eos_id)
        return cropped_contents

if __name__ == "__main__":
    df = pd.read_hdf('data/loaded/cpp_test.h5')
    pg = closed_dataset(df, crop_length=1200)
    # X, y = pg.gen()
