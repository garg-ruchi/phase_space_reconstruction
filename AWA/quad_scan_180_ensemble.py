import logging
from copy import deepcopy

import torch
from torchensemble import VotingRegressor
from torchensemble.utils.logging import set_logger


from modeling import Imager, InitialBeam, QuadScanTransport
from torch.utils.data import DataLoader, Dataset, random_split

logging.basicConfig(level=logging.INFO)
from image_processing import import_images

location = (
    "D:\\AWA\\phase_space_tomography_07_07_22" "\\Quadscan_data_matching_solenoid_180A"
)
base_fname = location + "\\DQ7_scan1_"

# process_images(base_fname, 10, 10)

all_k, all_images, all_charges, xx = import_images()
all_charges = torch.tensor(all_charges)
all_images = torch.tensor(all_images)
all_k = torch.tensor(all_k)
print(all_images.shape)


# create data loader
class ImageDataset(Dataset):
    def __init__(self, k, images):
        self.images = images
        self.k = k

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        return self.k[idx], self.images[idx]


def init_weights(m):
    if isinstance(m, torch.nn.Linear):
        torch.nn.init.xavier_uniform_(m.weight, gain=1.0)
        # torch.nn.init.xavier_uniform_(m.bias, gain=1.0)


class QuadScanModel(torch.nn.Module):
    def __init__(self, initial_beam, transport, imager):
        super(QuadScanModel, self).__init__()
        self.beam_generator = deepcopy(initial_beam)
        self.lattice = transport
        self.imager = imager

        self.beam_generator.apply(init_weights)

    def forward(self, K):
        initial_beam = self.beam_generator()
        output_beam = self.lattice(initial_beam, K)
        output_coords = torch.cat(
            [output_beam.x.unsqueeze(0), output_beam.y.unsqueeze(0)]
        )
        output_images = self.imager(output_coords)
        return output_images


defaults = {
    "s": torch.tensor(0.0).float(),
    "p0c": torch.tensor(65.0e6).float(),
    "mc2": torch.tensor(0.511e6).float(),
}

train_dset, test_dset = random_split(
    ImageDataset(
        all_k, all_images
    ), [17, 4]
)

train_dataloader = DataLoader(train_dset, batch_size=10)
test_dataloader = DataLoader(test_dset)

# define model components and model
bins = xx[0].T[0]
bandwidth = torch.tensor(1.0e-4)

module_kwargs = {
    "initial_beam": InitialBeam(1000, **defaults),
    "transport": QuadScanTransport(),
    "imager": Imager(bins, bandwidth)
}

logger = set_logger(log_file="log.txt", log_console_level="debug")


ensemble = VotingRegressor(
    estimator=QuadScanModel,
    estimator_args=module_kwargs,
    n_estimators=1,
    n_jobs=1
)


criterion = torch.nn.MSELoss(reduction="sum")
ensemble.set_criterion(criterion)

ensemble.set_optimizer(
    "Adam",
    lr=0.001
)


ensemble.fit(train_dataloader, epochs=10)
